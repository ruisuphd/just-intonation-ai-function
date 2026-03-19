import Link from "next/link";

const FEATURES = [
  {
    icon: "🎤",
    title: "Vocal Coach",
    description:
      "AI-powered vocal technique analysis and real-time feedback. Learn breathing, pitch, and register transitions like the pros.",
    href: "/coach/vocal",
  },
  {
    icon: "🎹",
    title: "Piano Coach",
    description:
      "Learn piano with intelligent feedback on notes, chords, timing and expression.",
    href: "/coach/piano",
  },
  {
    icon: "🎸",
    title: "Guitar Coach",
    description:
      "Master guitar with chord detection, strumming feedback and personalised exercises.",
    href: "/coach/guitar",
  },
];

const TESTIMONIALS = [
  {
    quote:
      "I felt the difference in just the first lesson. My voice is supported, and the notes are more sustainable.",
    author: "Marcus",
  },
  {
    quote:
      "I've unlocked my voice and everything clicked in only 6 lessons.",
    author: "Nicah",
  },
  {
    quote:
      "Your exercises are the right mix of fun and challenge.",
    author: "Katrin",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-[#fbfbfd]">
      <section className="mx-auto max-w-4xl px-6 py-24 text-center">
        <h1 className="text-4xl font-bold tracking-tight text-[#1d1d1f] sm:text-5xl md:text-6xl">
          Your AI Music Coach
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-[#6e6e73] leading-relaxed">
          Sing into your device and get instant feedback. Learn breathing, pitch,
          and technique from AI trained on world-class pedagogy.
        </p>
        <div className="mt-10 flex flex-wrap justify-center gap-4">
          <Link
            href="/login"
            className="inline-block rounded-xl bg-[#0071e3] px-8 py-3.5 text-base font-medium text-white transition hover:bg-[#0077ed]"
          >
            Get Started
          </Link>
          <Link
            href="/pricing"
            className="inline-block rounded-xl border border-[#d2d2d7] px-8 py-3.5 text-base font-medium text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
          >
            View Pricing
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="text-center text-2xl font-semibold text-[#1d1d1f]">
          How it works
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-[#6e6e73]">
          Turn on your mic, sing or speak, and send a message. Our AI analyses
          your pitch, rhythm, and technique—then gives specific, actionable
          feedback in seconds.
        </p>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-24">
        <h2 className="mb-10 text-center text-2xl font-semibold text-[#1d1d1f]">
          Coaches
        </h2>
        <div className="grid gap-6 sm:grid-cols-3">
          {FEATURES.map(({ icon, title, description, href }) => (
            <div
              key={title}
              className="rounded-2xl border border-[#d2d2d7] bg-white p-6 transition hover:border-[#0071e3]/30 hover:shadow-lg"
            >
              <span className="text-4xl">{icon}</span>
              <h3 className="mt-4 text-xl font-semibold text-[#1d1d1f]">
                {title}
              </h3>
              <p className="mt-2 text-[#6e6e73] leading-relaxed">{description}</p>
              {href !== "#" && (
                <Link
                  href={href}
                  className="mt-4 inline-block text-sm font-medium text-[#0071e3] hover:underline"
                >
                  Try it →
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-[#d2d2d7] bg-[#f5f5f7] py-20">
        <div className="mx-auto max-w-4xl px-6 text-center">
          <h2 className="text-2xl font-semibold text-[#1d1d1f]">
            Singers trust IntonationAI
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-3">
            {TESTIMONIALS.map(({ quote, author }) => (
              <blockquote
                key={author}
                className="rounded-xl bg-white p-6 text-left"
              >
                <p className="text-[#1d1d1f]">&ldquo;{quote}&rdquo;</p>
                <cite className="mt-4 block text-sm text-[#6e6e73]">
                  — {author}
                </cite>
              </blockquote>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-4xl px-6 py-24 text-center">
        <h2 className="text-2xl font-semibold text-[#1d1d1f]">
          Ready to improve your voice?
        </h2>
        <p className="mt-4 text-[#6e6e73]">
          Start with 3 free coaching sessions per week. Upgrade anytime.
        </p>
        <Link
          href="/login"
          className="mt-6 inline-block rounded-xl bg-[#0071e3] px-8 py-3.5 text-base font-medium text-white transition hover:bg-[#0077ed]"
        >
          Get Started Free
        </Link>
      </section>

      <footer className="border-t border-[#d2d2d7] py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6">
          <span className="text-sm text-[#6e6e73]">© IntonationAI</span>
          <div className="flex gap-6">
            <Link
              href="/pricing"
              className="text-sm text-[#0071e3] hover:underline"
            >
              Pricing
            </Link>
            <Link
              href="/login"
              className="text-sm text-[#0071e3] hover:underline"
            >
              Sign In
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
