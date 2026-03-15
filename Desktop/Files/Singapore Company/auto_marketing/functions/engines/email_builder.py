"""Rich HTML daily brief email builder and sender."""

from __future__ import annotations

import base64
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.logger import get_logger
from shared.models import DailyPostResult

logger = get_logger("engine.email_builder")


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    from_email: str
    use_tls: bool
    use_ssl: bool
    to_email: str

    @classmethod
    def from_env(cls, recipient_email: str | None = None) -> "SMTPConfig":
        # Try Firestore system_config first, then fall back to env vars
        fs_config: dict = {}
        try:
            from shared.firestore_client import get_doc

            fs_config = get_doc("system_config", "smtp_config", tenant_id=None) or {}
        except Exception:
            pass

        host = (fs_config.get("smtp_host") or os.getenv("SMTP_HOST", "")).strip()
        if not host:
            raise ValueError(
                "SMTP not configured. Go to Settings \u2192 Notifications to add SMTP credentials."
            )

        port = int(fs_config.get("smtp_port") or os.getenv("SMTP_PORT", "587"))
        username = (fs_config.get("smtp_user") or os.getenv("SMTP_USER", "")).strip() or None
        password = (fs_config.get("smtp_password") or os.getenv("SMTP_PASSWORD", "")).strip() or None
        from_email = (
            fs_config.get("smtp_from_email")
            or os.getenv("SMTP_FROM_EMAIL", "").strip()
            or (username or "")
        ).strip()
        if not from_email:
            raise ValueError("SMTP_FROM_EMAIL or SMTP_USER is required")

        to_email = (recipient_email or os.getenv("SMTP_TO_EMAIL", "")).strip()
        if not to_email:
            raise ValueError("SMTP_TO_EMAIL is required")

        fs_use_ssl = fs_config.get("smtp_use_ssl")
        fs_use_tls = fs_config.get("smtp_use_tls")
        if fs_use_ssl is not None:
            use_ssl = bool(fs_use_ssl)
        else:
            use_ssl = _as_bool(os.getenv("SMTP_USE_SSL"), default=False)
        if fs_use_tls is not None:
            use_tls = bool(fs_use_tls)
        else:
            use_tls = _as_bool(os.getenv("SMTP_USE_TLS"), default=not use_ssl)

        return cls(
            host=host,
            port=port,
            username=username,
            password=password,
            from_email=from_email,
            use_tls=use_tls,
            use_ssl=use_ssl,
            to_email=to_email,
        )


# ── HTML helpers ──────────────────────────────────────────────────────────────

_STYLES = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
       max-width: 700px; margin: 0 auto; padding: 20px; color: #1a1a1a; background: #f8f8f8; }
.card { background: #ffffff; border-radius: 8px; padding: 24px; margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
h1 { color: #0a0a0a; font-size: 22px; margin-bottom: 4px; }
h2 { color: #333; font-size: 16px; border-bottom: 2px solid #e5e5e5;
     padding-bottom: 8px; margin-top: 0; }
.subheading { color: #666; font-size: 13px; margin-bottom: 16px; }
.post-text { white-space: pre-wrap; line-height: 1.65; font-size: 15px; color: #222; }
.hashtags { color: #0073b1; font-size: 13px; margin-top: 8px; }
.hook { font-style: italic; color: #555; font-size: 13px; margin-bottom: 12px; }
.intel-item { border-left: 3px solid #0073b1; padding: 8px 12px; margin-bottom: 12px; background: #f0f7ff; border-radius: 0 4px 4px 0; }
.intel-score { font-weight: bold; color: #0073b1; }
.intel-title { font-weight: 600; font-size: 14px; }
.intel-summary { color: #555; font-size: 13px; margin-top: 4px; }
.intel-source { color: #888; font-size: 12px; }
.lead-card { border: 1px solid #e5e5e5; border-radius: 6px; padding: 16px; margin-bottom: 16px; }
.lead-header { font-weight: 700; font-size: 15px; }
.icp-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.icp-high { background: #d4edda; color: #155724; }
.icp-medium { background: #fff3cd; color: #856404; }
.icp-low { background: #e9ecef; color: #495057; }
.draft-block { background: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 4px;
               padding: 12px; margin-top: 10px; font-size: 13px; }
.draft-label { font-weight: 600; color: #333; font-size: 12px; text-transform: uppercase;
               letter-spacing: 0.5px; margin-bottom: 6px; }
.footer { color: #999; font-size: 11px; text-align: center; padding-top: 16px; }
img.post-image { max-width: 100%; border-radius: 6px; margin-bottom: 16px; display: block; }
.lang-flag { font-size: 18px; margin-right: 4px; }
.lang-section { margin-bottom: 20px; }
.no-leads { color: #888; font-style: italic; font-size: 14px; }
"""


def _score_colour(score: float) -> str:
    if score >= 0.8:
        return "#00875a"
    if score >= 0.6:
        return "#0073b1"
    return "#888"


def _post_status_label(post_status: str) -> str:
    if post_status == "ready":
        return "Post Ready"
    if post_status == "no_candidates":
        return "No Post Angle"
    return "Post Unavailable"


def _prospect_summary(lead_items: list[dict], prospect_items: list[dict]) -> str:
    if lead_items:
        count = len(lead_items)
        return f"{count} Lead{'s' if count != 1 else ''}"
    if prospect_items:
        count = len(prospect_items)
        return f"{count} Prospect{'s' if count != 1 else ''} To Review"
    return "No Prospects Today"


def _build_html(
    today: str,
    post_draft: DailyPostResult | None,
    post_status: str,
    image_bytes: bytes | None,
    intel_items: list[dict],
    lead_items: list[dict],
    prospect_items: list[dict],
    generated_at: datetime | None,
    timezone_name: str,
    company_name: str = "",
) -> str:
    subject_suffix = _prospect_summary(lead_items, prospect_items)
    header_suffix = f"{_post_status_label(post_status)} · {subject_suffix}"

    # ── Image block ───────────────────────────────────────────────────────────
    image_html = ""
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        image_html = f'<img class="post-image" src="data:image/png;base64,{b64}" alt="Generated post image">'

    # ── Post draft block ──────────────────────────────────────────────────────
    if post_draft:
        hashtags = " ".join(f"#{h.lstrip('#')}" for h in (post_draft.hashtags or []))
        post_html = f"""
        <div class="card">
          <h2>📝 Today's Post Draft</h2>
          {image_html}
          <div class="lang-section">
            <div><strong>Primary Angle</strong></div>
            <div class="hook">{_escape(post_draft.headline)}</div>
            <div class="post-text">{_escape(post_draft.linkedin_post)}</div>
            {'<div class="intel-summary" style="margin-top:10px"><strong>Why it matters:</strong> ' + _escape(post_draft.why_it_matters) + '</div>' if post_draft.why_it_matters else ''}
            <div class="hashtags">{_escape(hashtags)}</div>
          </div>
          <div class="draft-block">
            <div class="draft-label">X / Threads Variant</div>
            <div>{_escape(post_draft.x_post)}</div>
          </div>
          <div class="draft-block">
            <div class="draft-label">Instagram Caption</div>
            <div style="white-space:pre-wrap">{_escape(post_draft.instagram_caption)}</div>
          </div>
        </div>"""
    elif post_status == "no_candidates":
        post_html = '<div class="card"><h2>📝 Today\'s Post Draft</h2><p class="no-leads">No strong content angle found today.</p></div>'
    else:
        post_html = '<div class="card"><h2>📝 Today\'s Post Draft</h2><p class="no-leads">Post generation failed — check logs.</p></div>'

    # ── Intelligence block ────────────────────────────────────────────────────
    if intel_items:
        intel_rows = ""
        for item in intel_items:
            score = item.get("relevance_score") or 0.0
            title = item.get("title", "Untitled")
            source = item.get("source_name", "")
            summary = item.get("summary", "")
            url = item.get("source_url", "#")
            tags = item.get("tags") or []
            tag_str = " · ".join(tags[:3]) if tags else ""
            intel_rows += f"""
            <div class="intel-item">
              <span class="intel-score" style="color:{_score_colour(score)}">[{score:.2f}]</span>
              <span class="intel-title"> <a href="{url}" style="color:#0073b1;text-decoration:none">{_escape(title)}</a></span>
              {'<span class="intel-source"> · ' + _escape(source) + '</span>' if source else ''}
              {'<span class="intel-source"> · ' + _escape(tag_str) + '</span>' if tag_str else ''}
              {'<div class="intel-summary">' + _escape(summary) + '</div>' if summary else ''}
            </div>"""
        intel_html = f'<div class="card"><h2>📰 News Intelligence ({len(intel_items)} items)</h2>{intel_rows}</div>'
    else:
        intel_html = '<div class="card"><h2>📰 News Intelligence</h2><p class="no-leads">No new items today.</p></div>'

    # ── Leads block ───────────────────────────────────────────────────────────
    lead_sections: list[str] = []
    if lead_items:
        lead_rows = ""
        for i, lead in enumerate(lead_items, 1):
            company = lead.get("company_name", "Unknown Company")
            icp_fit = lead.get("icp_fit", "medium")
            icp_score = lead.get("icp_fit_score", 0.0)
            signal_summary = lead.get("signal_summary", "")
            icp_score_pct = round(icp_score * 100)
            badge_class = "icp-high" if icp_fit == "high" else "icp-medium"
            icp_label = icp_fit.upper()

            linkedin_dm = lead.get("linkedin_dm", "")
            cold_email = lead.get("cold_email") or {}
            email_subject = cold_email.get("subject", "")
            email_body = cold_email.get("body", "")
            channel = lead.get("recommended_channel", "")
            channel_reason = lead.get("channel_reason", "")
            approach_suggestion = lead.get("approach_suggestion", "")

            lead_rows += f"""
            <div class="lead-card">
              <div class="lead-header">LEAD {i}: {_escape(company)}
                <span class="icp-badge {badge_class}" style="margin-left:8px">ICP: {icp_label} — {icp_score_pct}%</span>
              </div>
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Signal:</strong> ' + _escape(signal_summary) + '</div>' if signal_summary else ''}
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Suggested first move:</strong> ' + _escape(approach_suggestion) + '</div>' if approach_suggestion else ''}
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Recommended channel:</strong> ' + _escape(channel) + '</div>' if channel else ''}
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Why this channel:</strong> ' + _escape(channel_reason) + '</div>' if channel_reason else ''}
              {'<div class="draft-block"><div class="draft-label">LinkedIn DM (copy-paste ready)</div><div>' + _escape(linkedin_dm) + '</div></div>' if linkedin_dm else ''}
              {'<div class="draft-block"><div class="draft-label">Cold Email</div><div><strong>Subject:</strong> ' + _escape(email_subject) + '</div><div style="margin-top:8px;white-space:pre-wrap">' + _escape(email_body) + '</div></div>' if email_body else ''}
            </div>"""
        lead_sections.append(
            f'<div class="card"><h2>🎯 Lead Opportunities ({len(lead_items)} found)</h2>{lead_rows}</div>'
        )

    if prospect_items:
        prospect_rows = ""
        for i, item in enumerate(prospect_items, 1):
            icp_score_pct = round((item.get("icp_fit_score") or 0.0) * 100)
            linkedin_dm = item.get("linkedin_dm", "")
            cold_email = item.get("cold_email") or {}
            email_subject = cold_email.get("subject", "")
            email_body = cold_email.get("body", "")
            prospect_rows += f"""
            <div class="lead-card">
              <div class="lead-header">PROSPECT {i}: {_escape(item.get("company_name", "Unknown"))}
                <span class="icp-badge icp-low" style="margin-left:8px">BEST-EFFORT — {icp_score_pct}%</span>
              </div>
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Signal:</strong> ' + _escape(item.get("signal_summary", "")) + '</div>' if item.get("signal_summary") else ''}
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Why this is tentative:</strong> ' + _escape(item.get("fit_reasoning", "")) + '</div>' if item.get("fit_reasoning") else ''}
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Suggested first move:</strong> ' + _escape(item.get("approach_suggestion", "")) + '</div>' if item.get("approach_suggestion") else ''}
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Recommended channel:</strong> ' + _escape(item.get("recommended_channel", "")) + '</div>' if item.get("recommended_channel") else ''}
              {'<div style="color:#555;font-size:13px;margin-top:6px"><strong>Why this channel:</strong> ' + _escape(item.get("channel_reason", "")) + '</div>' if item.get("channel_reason") else ''}
              {'<div class="draft-block"><div class="draft-label">LinkedIn Opener</div><div>' + _escape(linkedin_dm) + '</div></div>' if linkedin_dm else ''}
              {'<div class="draft-block"><div class="draft-label">Cold Email Draft</div><div><strong>Subject:</strong> ' + _escape(email_subject) + '</div><div style="margin-top:8px;white-space:pre-wrap">' + _escape(email_body) + '</div></div>' if email_body else ''}
            </div>"""
        lead_sections.append(
            f'<div class="card"><h2>🧭 Best-Effort Prospects ({len(prospect_items)} to review)</h2>{prospect_rows}</div>'
        )

    if not lead_sections:
        lead_sections.append(
            '<div class="card"><h2>🎯 Lead Opportunities</h2><p class="no-leads">No lead or prospect signals detected today.</p></div>'
        )

    if generated_at is None:
        try:
            generated_at = datetime.now(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            generated_at = datetime.now(timezone.utc)

    try:
        display_dt = generated_at.astimezone(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        display_dt = generated_at.astimezone(timezone.utc)
        timezone_name = "UTC"
    now_str = display_dt.strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Brief — {today}</title>
<style>{_STYLES}</style>
</head>
<body>
  <div class="card" style="background:#0073b1;color:#fff;padding:16px 24px;">
    <h1 style="color:#fff;margin:0">{_escape(company_name or 'AutoMark')} · Daily Brief</h1>
    <div style="color:#cce4f5;font-size:13px;margin-top:4px">{today} · {header_suffix}</div>
  </div>
  {post_html}
  {intel_html}
  {"".join(lead_sections)}
  <div class="footer">Generated by {_escape(company_name or 'AutoMark')} · {now_str} ({_escape(timezone_name)})</div>
</body>
</html>"""


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── SMTP sender ───────────────────────────────────────────────────────────────


def _send(*, config: SMTPConfig, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = config.from_email
    msg["To"] = config.to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if config.use_ssl:
        with smtplib.SMTP_SSL(config.host, config.port, timeout=30) as client:
            if config.username and config.password:
                client.login(config.username, config.password)
            client.send_message(msg)
        return

    with smtplib.SMTP(config.host, config.port, timeout=30) as client:
        client.ehlo()
        if config.use_tls:
            client.starttls()
            client.ehlo()
        if config.username and config.password:
            client.login(config.username, config.password)
        client.send_message(msg)


def send_daily_brief(
    *,
    today: str,
    post_draft: DailyPostResult | None,
    post_status: str,
    image_bytes: bytes | None,
    intel_items: list[dict],
    lead_items: list[dict],
    prospect_items: list[dict],
    generated_at: datetime | None = None,
    timezone_name: str = "UTC",
    recipient_email: str | None = None,
    company_name: str = "",
) -> None:
    """Build and send the daily HTML email digest."""
    try:
        smtp_config = SMTPConfig.from_env(recipient_email=recipient_email)
    except ValueError as exc:
        logger.error("email_builder.smtp_not_configured", extra={"error": str(exc)})
        raise

    subject = f"Daily Brief — {today} | {_post_status_label(post_status)} · {_prospect_summary(lead_items, prospect_items)}"

    html = _build_html(
        today=today,
        post_draft=post_draft,
        post_status=post_status,
        image_bytes=image_bytes,
        intel_items=intel_items,
        lead_items=lead_items,
        prospect_items=prospect_items,
        generated_at=generated_at,
        timezone_name=timezone_name,
        company_name=company_name,
    )

    _send(config=smtp_config, subject=subject, html_body=html)
    logger.info(
        "email_builder.sent",
        extra={
            "to": smtp_config.to_email,
            "intel_items": len(intel_items),
            "leads": len(lead_items),
            "prospects": len(prospect_items),
        },
    )
