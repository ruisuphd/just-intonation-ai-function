import type { Metadata } from "next";
import Link from "next/link";
import { getSiteUrl } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How IntoMarketing collects, uses, and protects personal data (GDPR, CCPA, PDPA).",
  alternates: {
    canonical: "/privacy",
  },
  openGraph: {
    url: `${getSiteUrl()}/privacy`,
  },
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to IntoMarketing
        </Link>
        <h1 className="mt-8 text-3xl font-bold">Privacy Policy</h1>
        <p className="mt-2 text-sm text-gray-500">Effective: March 17, 2026</p>
        <div className="prose prose-gray mt-8 max-w-none">

          <h2>1. Data Controller</h2>
          <p>
            IntoMarketing is operated by Intonation Labs Pte. Ltd., a company registered in Singapore
            (UEN: [registration number]). As the data controller, we determine the purposes and means by
            which your personal data is processed. If you have any questions or concerns regarding how
            we handle your personal data, please contact our privacy team at{" "}
            <a href="mailto:privacy@intonationlabs.com">privacy@intonationlabs.com</a>. We are committed
            to processing your personal data in accordance with applicable data protection laws, including
            the EU General Data Protection Regulation (GDPR), the UK GDPR, the California Consumer Privacy
            Act (CCPA), and Singapore&apos;s Personal Data Protection Act (PDPA).
          </p>

          <h2>2. Data We Collect</h2>
          <p>
            We collect information you provide directly and information generated through your use of the
            service. The categories of personal data we process include:
          </p>
          <ul>
            <li>
              <strong>Account data:</strong> When you sign in via Google OAuth, we receive your email
              address and display name from Google. We store this information to identify your account and
              personalise your experience.
            </li>
            <li>
              <strong>Company profile information:</strong> To generate relevant AI content, you provide
              us with your company name, industry, business description, competitor names, and target
              keywords. This information is stored in association with your account.
            </li>
            <li>
              <strong>AI-generated content:</strong> Social media posts, outreach email drafts,
              newsletters, and other content created using our AI tools are stored in your account so
              you can review, edit, and publish them.
            </li>
            <li>
              <strong>Usage data:</strong> We collect data about how you interact with the platform,
              including which features you use, the frequency of AI content generation requests, and
              API call metadata. This data is used in aggregate to improve the service.
            </li>
            <li>
              <strong>Payment information:</strong> Billing is handled entirely by Stripe, Inc. We do
              not store your credit card number, CVV, or full payment details on our servers. We retain
              only the Stripe customer ID, subscription status, and billing history records necessary
              for account management.
            </li>
            <li>
              <strong>Device and browser information:</strong> To monitor application stability and
              diagnose errors, we collect technical information such as your browser type, operating
              system, device type, IP address, and error stack traces via Sentry error tracking.
            </li>
          </ul>

          <h2>3. How We Use Your Data</h2>
          <p>
            We use the personal data we collect for the following purposes:
          </p>
          <ul>
            <li>
              <strong>Service delivery:</strong> Your account data and company profile information are
              used to authenticate you and to generate personalised AI content, market intelligence
              reports, and lead qualification results. Without this data, we cannot provide the core
              service.
            </li>
            <li>
              <strong>Account management:</strong> We use your email address to send transactional
              communications including account confirmation, password-related notices, and important
              service updates.
            </li>
            <li>
              <strong>Billing:</strong> We use your account and subscription data to manage your plan,
              process payments via Stripe, and generate invoices.
            </li>
            <li>
              <strong>Error tracking and security:</strong> Technical data collected via Sentry is used
              to identify, diagnose, and fix bugs, monitor performance, and detect and prevent
              fraudulent or abusive behaviour.
            </li>
            <li>
              <strong>Product improvement:</strong> Aggregated and anonymised usage analytics help us
              understand which features are most valuable and guide our product roadmap. We do not use
              your individual content or company-specific data for product improvement without your
              explicit consent.
            </li>
          </ul>

          <h2>4. Legal Basis for Processing (GDPR)</h2>
          <p>
            If you are located in the European Economic Area (EEA), the United Kingdom, or another
            jurisdiction that requires a lawful basis for processing personal data, we rely on the
            following bases:
          </p>
          <ul>
            <li>
              <strong>Performance of a contract (Article 6(1)(b) GDPR):</strong> Processing your
              account data, company profile, and AI-generated content is necessary to provide the
              IntoMarketing service under our Terms of Service.
            </li>
            <li>
              <strong>Legitimate interests (Article 6(1)(f) GDPR):</strong> We process technical and
              usage data for error tracking, fraud prevention, and service security. These legitimate
              interests are not overridden by your fundamental rights and freedoms, given the limited
              nature of the data collected and the safeguards we have in place.
            </li>
            <li>
              <strong>Consent (Article 6(1)(a) GDPR):</strong> Where we use analytics cookies or send
              you marketing communications, we rely on your consent. You may withdraw consent at any
              time without affecting the lawfulness of processing carried out prior to withdrawal.
            </li>
            <li>
              <strong>Legal obligation (Article 6(1)(c) GDPR):</strong> We retain payment records to
              comply with applicable tax and financial regulations.
            </li>
          </ul>

          <h2>5. AI Data Processing</h2>
          <p>
            IntoMarketing uses Google&apos;s Gemini AI models via the Vertex AI platform (Google Cloud) to
            generate content based on your inputs. When you request AI-generated content, the relevant
            portions of your company profile and any additional context you provide are transmitted to
            Google&apos;s Vertex AI API. Google&apos;s API Terms of Service and Privacy Notice govern Google&apos;s
            handling of this data. On paid API tiers, Google does not use data submitted through the
            API to train or improve its foundation models without explicit permission.
          </p>
          <p>
            We do not train our own machine learning models on your personal data, your company
            information, or your AI-generated content. AI-generated outputs are probabilistic in
            nature and may occasionally be inaccurate, incomplete, or not suitable for your use case.
            You are responsible for reviewing AI-generated content before publishing or distributing it.
            We recommend not submitting sensitive personal data (such as personal health information or
            financial details of individuals) as inputs to AI generation features.
          </p>

          <h2>6. Third-Party Data Processors</h2>
          <p>
            We engage the following third-party processors to help us deliver the service. Each processor
            is bound by a Data Processing Agreement (DPA) and processes data only on our instructions:
          </p>
          <ul>
            <li>
              <strong>Google Cloud Platform (Google LLC):</strong> We use Google Cloud as our primary
              infrastructure provider. This includes Firestore (database storage), Firebase Authentication
              (user authentication and session management), and Vertex AI (AI content generation). Data
              is primarily stored in Google Cloud&apos;s Singapore region (asia-southeast1).
            </li>
            <li>
              <strong>Stripe, Inc.:</strong> Stripe is our payment processor. Stripe collects and
              processes your payment card information directly and is certified as PCI DSS Level 1
              compliant. Stripe may transfer data to the United States and other jurisdictions where it
              operates.
            </li>
            <li>
              <strong>Sentry (Functional Software, Inc.):</strong> We use Sentry for real-time error
              tracking and application performance monitoring. Sentry may collect browser information,
              IP addresses, and error stack traces. Sentry is SOC 2 Type II certified.
            </li>
          </ul>
          <p>
            We do not sell your personal data to any third party, and we do not share your data with
            third parties for their own marketing purposes.
          </p>

          <h2>7. Data Retention</h2>
          <p>
            We retain personal data for no longer than is necessary for the purposes described in this
            policy, unless a longer retention period is required by law. Our retention schedule is as
            follows:
          </p>
          <ul>
            <li>
              <strong>Account data and company profile:</strong> Retained for as long as your account
              is active. Upon receiving a verified account deletion request, we will delete or anonymise
              this data within 30 days, except where retention is required by law.
            </li>
            <li>
              <strong>AI-generated content:</strong> Stored within your account for as long as your
              account is active, and deleted within 30 days of account deletion.
            </li>
            <li>
              <strong>Usage logs:</strong> Retained for 90 days for debugging, security monitoring, and
              aggregate analytics, after which they are automatically purged.
            </li>
            <li>
              <strong>Payment records:</strong> Retained for as long as required by applicable tax and
              financial regulations, which is typically 7 years in most jurisdictions.
            </li>
            <li>
              <strong>Error and crash reports:</strong> Retained by Sentry for 90 days in accordance
              with our Sentry plan configuration.
            </li>
          </ul>

          <h2>8. International Data Transfers</h2>
          <p>
            Our primary data processing infrastructure is located in Google Cloud&apos;s Singapore region
            (asia-southeast1), which means most of your data is processed within Singapore. However,
            some of our third-party processors, including Stripe and Sentry, are headquartered in the
            United States and may process personal data there or in other jurisdictions.
          </p>
          <p>
            Where we transfer personal data from the EEA, UK, or Switzerland to countries that have not
            been granted an adequacy decision by the European Commission, we rely on Standard Contractual
            Clauses (SCCs) adopted by the European Commission as the transfer mechanism to ensure an
            adequate level of protection. Copies of the applicable SCCs can be provided upon request
            at <a href="mailto:privacy@intonationlabs.com">privacy@intonationlabs.com</a>.
          </p>

          <h2>9. Your Rights</h2>
          <p>
            Depending on your location, you may have the following rights in relation to your personal
            data. To exercise any of these rights, you can use the self-service options in your account
            settings or contact us at{" "}
            <a href="mailto:privacy@intonationlabs.com">privacy@intonationlabs.com</a>. We will respond
            to all verified requests within 30 days (or within the timeframe required by applicable law).
          </p>
          <ul>
            <li>
              <strong>Right of access:</strong> You have the right to request a copy of the personal
              data we hold about you. You can view much of your data directly in the Settings section
              of your account.
            </li>
            <li>
              <strong>Right to rectification:</strong> If any personal data we hold about you is
              inaccurate or incomplete, you have the right to request correction. Most account and
              profile information can be edited directly in Settings.
            </li>
            <li>
              <strong>Right to erasure (&quot;right to be forgotten&quot;):</strong> You may request deletion of
              your personal data by navigating to Settings &gt; Delete Account, or by emailing
              privacy@intonationlabs.com. We will delete your data within 30 days, subject to any legal
              retention obligations.
            </li>
            <li>
              <strong>Right to data portability:</strong> You can export your data (including your
              company profile and AI-generated content) in a structured, machine-readable format via
              Settings &gt; Export Data.
            </li>
            <li>
              <strong>Right to restriction of processing:</strong> In certain circumstances, you may
              request that we restrict the processing of your personal data while a dispute is being
              resolved.
            </li>
            <li>
              <strong>Right to object:</strong> You have the right to object to processing based on
              legitimate interests. We will cease processing unless we can demonstrate compelling
              legitimate grounds that override your interests.
            </li>
            <li>
              <strong>Right to withdraw consent:</strong> Where processing is based on consent, you
              may withdraw it at any time. Withdrawing consent does not affect the lawfulness of
              processing prior to withdrawal.
            </li>
            <li>
              <strong>Right to lodge a complaint:</strong> If you believe we have not handled your
              personal data in accordance with applicable law, you have the right to lodge a complaint
              with your local data protection authority. EEA residents may contact the supervisory
              authority in their Member State of habitual residence.
            </li>
          </ul>

          <h2>10. Cookies and Tracking Technologies</h2>
          <p>
            We use cookies and similar tracking technologies on the IntoMarketing platform. Cookies are
            small text files stored on your device that help us provide and improve our services.
          </p>
          <ul>
            <li>
              <strong>Essential cookies:</strong> Firebase Authentication uses session cookies to keep
              you logged in and maintain your authenticated session. These cookies are strictly necessary
              for the service to function and cannot be disabled without affecting functionality.
            </li>
            <li>
              <strong>Error tracking:</strong> Sentry may use browser storage mechanisms to track error
              sessions and correlate bug reports. This is subject to your cookie consent preferences
              where consent is required by law.
            </li>
            <li>
              <strong>Analytics cookies:</strong> If we introduce additional analytics tools in the
              future, we will request your consent before placing analytics cookies and will update this
              policy accordingly.
            </li>
          </ul>
          <p>
            We do not currently use third-party advertising or marketing cookies. You can manage your
            cookie preferences through our cookie consent banner, which is displayed upon first visiting
            the platform. You may also control cookies through your browser settings; however, disabling
            essential cookies may impair your ability to use the service.
          </p>

          <h2>11. Children&apos;s Privacy</h2>
          <p>
            The IntoMarketing service is intended for business use and is not directed at individuals
            under the age of 16. We do not knowingly collect or solicit personal data from children
            under 16. If you are under 16, please do not use the service or provide any personal
            information to us. If we become aware that we have inadvertently collected personal data
            from a child under 16 without verifiable parental or guardian consent, we will take steps
            to delete that information as soon as possible. If you believe we may have collected data
            from a child under 16, please contact us at{" "}
            <a href="mailto:privacy@intonationlabs.com">privacy@intonationlabs.com</a>.
          </p>

          <h2>12. Data Security</h2>
          <p>
            We implement appropriate technical and organisational measures to protect your personal data
            against unauthorised access, accidental loss, destruction, or disclosure. Our security
            practices include:
          </p>
          <ul>
            <li>
              <strong>Encryption in transit:</strong> All data transmitted between your browser and
              our servers is encrypted using TLS (Transport Layer Security) 1.2 or higher.
            </li>
            <li>
              <strong>Encryption at rest:</strong> Data stored in Google Cloud Firestore is encrypted
              at rest by Google Cloud using AES-256 encryption by default.
            </li>
            <li>
              <strong>Access controls:</strong> Access to production systems and personal data is
              restricted to authorised personnel on a need-to-know basis. We use Firebase Security
              Rules to enforce data access policies at the database level.
            </li>
            <li>
              <strong>Security monitoring:</strong> We use Sentry and Google Cloud security tooling to
              monitor for anomalous behaviour and potential security incidents.
            </li>
            <li>
              <strong>Regular security reviews:</strong> We conduct periodic reviews of our security
              practices and update our controls as the threat landscape evolves.
            </li>
          </ul>
          <p>
            While we take data security seriously, no system is completely immune to security risks.
            In the event of a personal data breach that is likely to result in a risk to your rights
            and freedoms, we will notify affected users and the relevant supervisory authorities as
            required by applicable law.
          </p>

          <h2>13. Changes to This Policy</h2>
          <p>
            We may update this Privacy Policy from time to time to reflect changes in our practices,
            technology, legal requirements, or for other operational reasons. When we make material
            changes — for example, changes to how we use your data, the types of data we collect, or
            the third-party processors we engage — we will notify you by email at least 30 days before
            the changes take effect. The updated policy will also be posted on this page with a revised
            effective date. For non-material changes, we may update this page without prior notice.
            Your continued use of the IntoMarketing service after the effective date of any changes
            constitutes your acceptance of the updated Privacy Policy.
          </p>

          <h2>14. CCPA Addendum — California Residents</h2>
          <p>
            If you are a California resident, you have additional rights under the California Consumer
            Privacy Act (CCPA) and the California Privacy Rights Act (CPRA). This section supplements
            the rest of our Privacy Policy and applies solely to California residents.
          </p>
          <ul>
            <li>
              <strong>We do not sell your personal information.</strong> We have not sold and do not
              sell personal information to third parties, as defined under the CCPA. We also do not
              share personal information for cross-context behavioural advertising purposes.
            </li>
            <li>
              <strong>Right to know:</strong> You have the right to request that we disclose the
              categories and specific pieces of personal information we have collected about you in the
              past 12 months, the categories of sources from which it was collected, the business or
              commercial purposes for which it was collected, and the categories of third parties with
              whom it is shared.
            </li>
            <li>
              <strong>Right to delete:</strong> You have the right to request deletion of personal
              information we have collected about you, subject to certain exceptions (such as data we
              are required to retain by law or data necessary to complete a transaction you requested).
            </li>
            <li>
              <strong>Right to correct:</strong> You have the right to request that we correct
              inaccurate personal information we hold about you.
            </li>
            <li>
              <strong>Right to opt out:</strong> As we do not sell personal information or engage in
              cross-context behavioural advertising, there is currently no opt-out mechanism required.
              If our practices change, we will update this policy and provide an opt-out mechanism.
            </li>
            <li>
              <strong>Right to non-discrimination:</strong> We will not discriminate against you for
              exercising any of your CCPA rights. We will not deny you goods or services, charge you
              different prices, or provide a different level of service because you exercised your
              privacy rights.
            </li>
          </ul>
          <p>
            To submit a CCPA request, please email us at{" "}
            <a href="mailto:privacy@intonationlabs.com">privacy@intonationlabs.com</a> with the subject
            line &quot;CCPA Privacy Request&quot;. We will verify your identity before processing the request and
            will respond within 45 days, with an extension of up to 90 days where reasonably necessary.
          </p>

          <h2>15. Contact Us</h2>
          <p>
            If you have any questions, concerns, or requests regarding this Privacy Policy or our data
            processing practices, please contact us:
          </p>
          <ul>
            <li>
              <strong>Email:</strong>{" "}
              <a href="mailto:privacy@intonationlabs.com">privacy@intonationlabs.com</a>
            </li>
            <li>
              <strong>Company:</strong> Intonation Labs Pte. Ltd.
            </li>
            <li>
              <strong>Registered address:</strong> Singapore
            </li>
          </ul>
          <p>
            We aim to acknowledge all privacy-related enquiries within 2 business days and to resolve
            them within 30 days. If you are not satisfied with our response, you have the right to
            lodge a complaint with your local data protection authority.
          </p>

        </div>
      </div>
    </div>
  );
}
