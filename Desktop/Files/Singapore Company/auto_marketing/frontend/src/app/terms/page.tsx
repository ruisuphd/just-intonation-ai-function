/* eslint-disable react/no-unescaped-entities */
import type { Metadata } from "next";
import Link from "next/link";
import { getSiteUrl } from "@/lib/site-url";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "Terms governing use of the IntoMarketing platform and subscriptions.",
  alternates: {
    canonical: "/terms",
  },
  openGraph: {
    url: `${getSiteUrl()}/terms`,
  },
};

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to IntoMarketing
        </Link>
        <h1 className="mt-8 text-3xl font-bold">Terms of Service</h1>
        <p className="mt-2 text-sm text-gray-500">Effective: March 17, 2026</p>
        <div className="prose prose-gray mt-8 max-w-none">

          <h2>1. Acceptance of Terms</h2>
          <p>
            These Terms of Service ("Terms") constitute a legally binding agreement between you ("User", "you", or
            "your") and Intonation Labs Pte. Ltd., a company incorporated in Singapore ("Intonation Labs", "we", "us",
            or "our"), governing your access to and use of the IntoMarketing platform and any related services
            (collectively, the "Service"). By creating an account, accessing, or using IntoMarketing in any way, you
            acknowledge that you have read, understood, and agree to be bound by these Terms and our Privacy Policy.
            If you are using the Service on behalf of an organisation or business, you represent and warrant that you
            have the authority to bind that entity to these Terms, and references to "you" shall include that entity.
            If you do not agree to these Terms, you must immediately cease using the Service and delete your account.
            We reserve the right to update these Terms at any time; continued use of the Service following notice of
            changes constitutes your acceptance of the revised Terms.
          </p>

          <h2>2. Service Description</h2>
          <p>
            IntoMarketing is an AI-powered marketing automation platform designed to help businesses and marketing
            professionals accelerate their digital marketing workflows. The Service provides a suite of tools
            including daily content generation across social media channels, market intelligence and competitive
            analysis, lead qualification and scoring, outreach message drafting, and newsletter creation and
            management. Our platform leverages large language model technology to generate marketing copy, suggest
            campaign strategies, and surface actionable insights from publicly available market data. The Service
            is provided as software-as-a-service (SaaS) and is accessible via web browser at intomarketing.io.
            Features and capabilities may vary depending on your subscription plan. We continuously improve and
            expand the Service, and certain features may be added, modified, or removed over time.
          </p>

          <h2>3. Account Registration</h2>
          <p>
            To access IntoMarketing, you must register for an account using either a valid email address and
            password or by authenticating through Google OAuth (collectively, "Account Credentials"). You agree
            to provide accurate, current, and complete information during registration and to keep your account
            information up to date at all times. Each individual person may hold only one active account; creating
            multiple accounts for a single user is prohibited. You are solely responsible for maintaining the
            confidentiality of your Account Credentials and for all activities that occur under your account,
            whether or not authorised by you. You must notify us immediately at support@intonationlabs.com if you
            suspect any unauthorised use of your account or any other breach of security. We will not be liable
            for any loss or damage arising from your failure to maintain the security of your Account Credentials.
            You must be at least 18 years of age, or the age of legal majority in your jurisdiction, to create
            an account and use the Service.
          </p>

          <h2>4. Plans &amp; Pricing</h2>
          <p>
            IntoMarketing offers two subscription tiers: (a) <strong>Starter</strong>, a free plan with limited
            usage quotas across all features, available to all registered users; and (b) <strong>Pro</strong>,
            a paid plan priced at USD $29.00 per month, which provides expanded usage quotas, priority processing,
            and access to advanced features as described on our pricing page. Pro plan fees are billed on a
            monthly basis and processed securely through Stripe, Inc. All prices are stated in United States
            Dollars and are exclusive of any applicable taxes, levies, or duties imposed by your local
            jurisdiction, which remain your sole responsibility. We reserve the right to modify our pricing and
            plan structures at any time, provided that we will give you at least 30 days' prior written notice
            of any price increases via email. Continued use of the Pro plan following the effective date of a
            price change constitutes your acceptance of the new pricing. We may also offer promotional pricing
            or discounts, which are subject to their own terms and may be withdrawn at any time.
          </p>

          <h2>5. Acceptable Use</h2>
          <p>
            You agree to use IntoMarketing only for lawful purposes and in accordance with these Terms. The
            following activities are expressly prohibited:
          </p>
          <ul>
            <li>
              Sending unsolicited commercial messages (spam) or using the Service to facilitate bulk unsolicited
              outreach in violation of applicable anti-spam laws, including the Singapore Spam Control Act, the
              CAN-SPAM Act, or GDPR.
            </li>
            <li>
              Generating, publishing, or distributing illegal, defamatory, obscene, harassing, threatening, or
              otherwise objectionable content through the Service.
            </li>
            <li>
              Scraping, crawling, data-mining, or otherwise extracting data from the Service through automated
              means without our express prior written consent.
            </li>
            <li>
              Circumventing, bypassing, or manipulating usage limits, rate limits, quotas, or any other technical
              restrictions imposed by the Service.
            </li>
            <li>
              Creating accounts through automated means, using bots or scripts to register accounts, or
              maintaining fictitious or fraudulent user profiles.
            </li>
            <li>
              Attempting to gain unauthorised access to any part of the Service, our servers, databases, or
              related infrastructure, or interfering with the proper operation of the Service.
            </li>
            <li>
              Using the Service to infringe, misappropriate, or violate the intellectual property, privacy, or
              other legal rights of any third party.
            </li>
          </ul>
          <p>
            We reserve the right to investigate any suspected violation of this section and to take appropriate
            action, including suspending or terminating your account without prior notice.
          </p>

          <h2>6. AI-Generated Content</h2>
          <p>
            The Service uses Google Gemini and other artificial intelligence models to generate marketing copy,
            outreach messages, market summaries, and other content ("AI-Generated Content") based on your inputs
            and instructions. You acknowledge and agree that AI-Generated Content is produced algorithmically and
            may not be accurate, complete, original, or suitable for your particular use case. We make no
            representations or warranties regarding the accuracy, factual correctness, uniqueness, or fitness for
            purpose of any AI-Generated Content. You are solely responsible for reviewing, editing, and verifying
            all AI-Generated Content before publishing or distributing it, and for ensuring that any content you
            publish complies with the terms of service and community guidelines of the relevant third-party
            platforms (including but not limited to LinkedIn, X (formerly Twitter), Instagram, and Facebook).
            AI-Generated Content does not constitute legal advice, financial advice, medical advice, or any other
            form of professional advice, and should not be relied upon as such. You should seek independent
            professional advice where appropriate. Intonation Labs shall not be liable for any loss, damage, or
            legal consequence arising from your use or publication of AI-Generated Content.
          </p>

          <h2>7. Intellectual Property</h2>
          <p>
            As between you and Intonation Labs, you retain all ownership rights in the data, content, and
            information you submit to the Service ("User Input") and in the AI-Generated Content produced on
            your behalf. Intonation Labs retains all rights, title, and interest in and to the IntoMarketing
            platform, software, algorithms, user interface, visual design, branding, trademarks (including the
            IntoMarketing name and logo), trade secrets, and all other proprietary elements of the Service
            ("Platform IP"). Nothing in these Terms transfers any Platform IP rights to you. By submitting User
            Input and using the Service, you grant Intonation Labs a non-exclusive, worldwide, royalty-free
            licence to process, store, copy, and use your User Input and any resulting AI-Generated Content
            solely to the extent necessary to provide, maintain, and improve the Service for you. We will not
            sell your User Input to third parties or use it to train AI models without your explicit consent.
            If you provide feedback, suggestions, or ideas about the Service, you grant us an irrevocable,
            perpetual, royalty-free licence to use such feedback without any obligation to you.
          </p>

          <h2>8. Payment Terms</h2>
          <p>
            Pro plan subscriptions are billed on a monthly recurring basis. By subscribing to the Pro plan,
            you authorise Intonation Labs to charge your payment method on file via Stripe on the same date each
            month (or the nearest valid calendar date if that date does not exist in a given month). You may
            cancel your Pro subscription at any time through the Settings page within IntoMarketing or via the
            Stripe customer portal; cancellation takes effect at the end of the current billing period, after
            which your account will be downgraded to the Starter plan. We do not provide refunds or credits for
            partial months of service, unused features, or periods of inactivity. If your payment fails for any
            reason, we will notify you via email and may retry the charge; if the payment remains outstanding
            after reasonable attempts to collect, your account may be automatically downgraded to the Starter
            plan until a valid payment method is provided. All subscription fees are non-refundable except as
            expressly required by applicable law or at our sole discretion. In the event of a dispute regarding
            charges, please contact us at support@intonationlabs.com within 30 days of the charge.
          </p>

          <h2>9. Data &amp; Privacy</h2>
          <p>
            Your privacy is important to us. Our collection, use, storage, and disclosure of personal data in
            connection with the Service is governed by our Privacy Policy, available at{" "}
            <Link href="/privacy" className="text-blue-600 hover:underline">
              /privacy
            </Link>
            , which is incorporated
            into these Terms by reference. By using the Service, you consent to the processing of your personal
            data as described in our Privacy Policy. We process personal data in accordance with applicable data
            protection laws, including the EU General Data Protection Regulation (GDPR) and the California
            Consumer Privacy Act (CCPA), where applicable. If you are located in the European Economic Area
            or the United Kingdom, you may have additional rights regarding your personal data, including the
            right to access, rectify, erase, restrict processing, and data portability, as described in our
            Privacy Policy. For any data protection queries or to exercise your rights, please contact our
            data protection team at support@intonationlabs.com.
          </p>

          <h2>10. Service Availability</h2>
          <p>
            Intonation Labs will use commercially reasonable efforts to ensure that IntoMarketing is available
            and operational. However, we do not warrant or guarantee any specific level of uptime, availability,
            or service continuity. No service level agreement (SLA) is provided for users on the Starter (free)
            plan. The Service may be temporarily unavailable due to scheduled maintenance, emergency maintenance,
            third-party service disruptions (including cloud infrastructure and AI provider outages), or other
            circumstances beyond our reasonable control. We will endeavour to provide advance notice of scheduled
            maintenance windows where practicable. We reserve the right to modify, update, suspend, or
            discontinue any aspect of the Service at any time, with or without prior notice, though we will use
            reasonable efforts to provide at least 30 days' notice before discontinuing the Service entirely.
            We shall not be liable to you or any third party for any modification, suspension, or discontinuation
            of the Service.
          </p>

          <h2>11. Account Termination</h2>
          <p>
            Either party may terminate these Terms and close your IntoMarketing account at any time. You may
            delete your account at any time through the account deletion option in the Settings page. Upon
            deletion, we will permanently remove your account data in accordance with our Privacy Policy, subject
            to any retention obligations imposed by applicable law. Intonation Labs reserves the right to suspend,
            restrict, or terminate your account immediately and without prior notice if we determine, in our sole
            discretion, that you have violated these Terms, engaged in fraudulent or illegal activity, or posed
            a risk to the integrity or security of the Service or other users. In the event of termination for
            cause, you will not be entitled to any refund of prepaid fees. Upon any termination, your right to
            access and use the Service will immediately cease, and you must immediately stop using the Service.
            Provisions of these Terms that by their nature should survive termination shall survive, including
            but not limited to intellectual property, limitation of liability, indemnification, and governing law.
          </p>

          <h2>12. Limitation of Liability</h2>
          <p>
            THE SERVICE IS PROVIDED ON AN "AS IS" AND "AS AVAILABLE" BASIS, WITHOUT WARRANTIES OF ANY KIND,
            EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY,
            FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT, AND ACCURACY OF INFORMATION. TO THE MAXIMUM
            EXTENT PERMITTED BY APPLICABLE LAW, INTONATION LABS PTE. LTD. AND ITS OFFICERS, DIRECTORS,
            EMPLOYEES, AGENTS, AND AFFILIATES SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL,
            CONSEQUENTIAL, PUNITIVE, OR EXEMPLARY DAMAGES, INCLUDING BUT NOT LIMITED TO LOSS OF PROFITS,
            LOSS OF REVENUE, LOSS OF DATA, LOSS OF GOODWILL, OR BUSINESS INTERRUPTION, ARISING OUT OF OR
            RELATING TO YOUR USE OF OR INABILITY TO USE THE SERVICE, EVEN IF WE HAVE BEEN ADVISED OF THE
            POSSIBILITY OF SUCH DAMAGES. TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, OUR TOTAL
            CUMULATIVE LIABILITY TO YOU FOR ANY AND ALL CLAIMS ARISING OUT OF OR RELATING TO THESE TERMS OR
            THE SERVICE SHALL NOT EXCEED THE GREATER OF (A) THE TOTAL FEES PAID BY YOU TO INTONATION LABS
            IN THE TWELVE (12) MONTHS IMMEDIATELY PRECEDING THE EVENT GIVING RISE TO THE CLAIM, OR (B)
            ONE HUNDRED UNITED STATES DOLLARS (USD $100). THE LIMITATIONS IN THIS SECTION SHALL APPLY
            REGARDLESS OF THE FORM OF ACTION, WHETHER IN CONTRACT, TORT, STRICT LIABILITY, OR OTHERWISE.
            SOME JURISDICTIONS DO NOT ALLOW THE EXCLUSION OR LIMITATION OF CERTAIN DAMAGES, SO THE ABOVE
            LIMITATIONS MAY NOT APPLY TO YOU IN FULL.
          </p>

          <h2>13. Indemnification</h2>
          <p>
            You agree to defend, indemnify, and hold harmless Intonation Labs Pte. Ltd. and its officers,
            directors, employees, agents, licensors, and service providers from and against any and all claims,
            liabilities, damages, judgments, awards, losses, costs, expenses, and fees (including reasonable
            legal fees) arising out of or relating to: (a) your use of the Service; (b) any content you submit,
            post, generate using, or distribute through the Service, including AI-Generated Content that you
            publish to third-party platforms; (c) your violation of these Terms; (d) your violation of any
            applicable law, regulation, or third-party right, including the terms of service or community
            guidelines of any platform to which you publish content; or (e) any dispute between you and a
            third party. We reserve the right, at our own expense, to assume the exclusive defence and control
            of any matter otherwise subject to indemnification by you, in which case you agree to cooperate
            fully with us in asserting any available defences.
          </p>

          <h2>14. Governing Law</h2>
          <p>
            These Terms and any dispute or claim arising out of or in connection with them or their subject
            matter or formation (including non-contractual disputes or claims) shall be governed by and
            construed in accordance with the laws of the Republic of Singapore, without regard to its conflict
            of law principles. You and Intonation Labs Pte. Ltd. irrevocably submit to the exclusive
            jurisdiction of the courts of Singapore to settle any dispute or claim arising out of or in
            connection with these Terms or the Service. Notwithstanding the foregoing, Intonation Labs reserves
            the right to seek injunctive or other equitable relief in any court of competent jurisdiction to
            prevent actual or threatened infringement, misappropriation, or violation of its intellectual
            property rights or confidential information. The United Nations Convention on Contracts for the
            International Sale of Goods does not apply to these Terms.
          </p>

          <h2>15. Changes to Terms</h2>
          <p>
            We reserve the right to modify these Terms at any time. For material changes — including changes
            to pricing, limitations of liability, dispute resolution, or your key rights and obligations —
            we will provide at least 30 days' prior written notice via email to the address associated with
            your account and/or by posting a prominent notice within the Service. For minor or non-material
            changes, we may update the Terms with shorter notice, reflected in the updated "Effective" date
            at the top of this page. It is your responsibility to ensure that your contact email address
            remains current and that you review any notices we send. Your continued use of the Service after
            the effective date of any revised Terms constitutes your acceptance of those changes. If you do
            not agree to the revised Terms, you must stop using the Service and, if applicable, cancel your
            subscription before the changes take effect.
          </p>

          <h2>16. Contact</h2>
          <p>
            If you have any questions, concerns, or requests regarding these Terms of Service or the Service
            generally, please contact Intonation Labs Pte. Ltd. by email at{" "}
            <a href="mailto:support@intonationlabs.com" className="text-blue-600 hover:underline">
              support@intonationlabs.com
            </a>
            . We aim to respond to all enquiries within five (5) business days. For formal legal notices,
            please address correspondence to Intonation Labs Pte. Ltd., Singapore. These Terms were last
            reviewed and updated on March 17, 2026.
          </p>

        </div>
      </div>
    </div>
  );
}
