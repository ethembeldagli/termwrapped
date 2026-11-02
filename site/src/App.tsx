import { useRef } from "react"
import Balatro from "@/components/Balatro"
import Iridescence from "@/components/Iridescence"
import CountUp from "@/components/CountUp"
import DecryptedText from "@/components/DecryptedText"
import GradientText from "@/components/GradientText"
import { ScrollVelocity } from "@/components/ScrollVelocity"
import { Terminal, TypingAnimation, AnimatedSpan } from "@/components/ui/terminal"
import { RainbowButton } from "@/components/ui/rainbow-button"
import { CardContainer, CardBody, CardItem } from "@/components/ui/3d-card"
import { BentoGrid, BentoGridItem } from "@/components/ui/bento-grid"
import Footer from "@/components/monet/Footer"

const REPO = "https://github.com/ethembeldagli/termwrapped"
const INSTALL = "curl -fsSL https://raw.githubusercontent.com/ethembeldagli/termwrapped/main/install.sh | sh"

const Kicker = ({ children }: { children: React.ReactNode }) => (
  <p className="mono text-xs tracking-[0.5em] uppercase text-white/70">{children}</p>
)

const Num = ({ to, color }: { to: number; color: string }) => (
  <CountUp to={to} separator="," duration={2.2} className="block font-bold leading-none tracking-tighter text-[clamp(5rem,22vw,20rem)]" style={{ color }} />
)

export default function App() {
  const scroller = useRef<HTMLElement>(null)
  return (
    <main ref={scroller} className="h-svh overflow-y-scroll snap-y snap-mandatory">
      {/* 01 — the cover slide */}
      <section className="slide grid place-items-center text-center">
        <div className="absolute inset-0"><Balatro color1="#ff5fd2" color2="#ffb86b" color3="#12031f" className="h-full w-full" /></div>
        <div className="relative z-10 px-6">
          <Kicker>Your year in the terminal · {new Date().getFullYear()}</Kicker>
          <h1 className="mt-6 font-bold leading-[0.85] tracking-tighter text-[clamp(3.5rem,13vw,13rem)]">
            <GradientText colors={["#ffffff", "#ffb86b", "#ff5fd2", "#ffffff"]} animationSpeed={6}>Terminal</GradientText>
            <span className="block">Wrapped</span>
          </h1>
          <DecryptedText text="Spotify Wrapped, but for your terminal." animateOn="view" sequential speed={35} className="mono text-lg" parentClassName="mt-8 block" />
        </div>
        <p className="mono absolute bottom-8 left-1/2 -translate-x-1/2 text-xs text-white/60 animate-bounce">scroll ↓</p>
      </section>

      {/* 02 — a stat slide, the way the app shows them */}
      <section className="slide grid place-items-center text-center">
        <div className="absolute inset-0"><Iridescence color={[0.2, 0.9, 1]} speed={0.6} amplitude={0.15} brightness={0.55} className="h-full w-full" /></div>
        <div className="relative z-10 drop-shadow-[0_4px_30px_rgba(0,0,0,0.6)]">
          <Kicker>Commands</Kicker>
          <p className="mt-4 text-2xl">You ran</p>
          <Num to={4394} color="#ffffff" />
          <p className="text-2xl">commands, using 19 different programs.</p>
          <p className="mono mt-6 text-sm text-white/70">Your keyboard felt that.</p>
        </div>
      </section>

      {/* 03 — what it counts, as a speeding band */}
      <section className="slide flex flex-col justify-center gap-4 bg-[#12031f]">
        <ScrollVelocity scrollContainerRef={scroller} texts={["git · vim · ls · cd · cargo · sudo ·", "kernel panics · dist-upgrades · 3 AM commits ·"]} velocity={60} className="px-4 font-bold uppercase text-[#ff5fd2]" fontSize="clamp(3rem,9vw,8rem)" />
        <div className="mx-auto max-w-xl px-6 text-center">
          <Kicker>What it reads</Kicker>
          <p className="mt-4 text-xl text-white/80">Your shell history, git log, package manager and Steam library. Read locally, summed up, never uploaded.</p>
        </div>
      </section>

      {/* 04 — everything in the slideshow */}
      <section className="slide flex items-center bg-[#0b0214] px-6 py-16">
        <div className="mx-auto w-full max-w-5xl">
          <Kicker>Ten slides, one year</Kicker>
          <h2 className="mt-3 mb-8 text-5xl font-bold tracking-tight">Every slide is about you.</h2>
          <BentoGrid className="grid-cols-1 sm:grid-cols-2 md:grid-cols-3 md:auto-rows-[11rem]">
            {[
              ["Top 5 commands", "The things you typed most, as a bar chart.", "#ff5fd2", "md:col-span-2", "git 904"],
              ["Oops", "Every `gti` instead of `git`.", "#ffb86b", "", "32 typos"],
              ["Night owl", "When you actually code.", "#9d8cff", "", "3 AM"],
              ["Gaming", "Playtime straight from Steam.", "#3ee6ff", "", "313h"],
              ["Your personality", "Vim Monk, Night Owl, Distro Hopper, or one of twelve others.", "#b6ff5c", "md:col-span-2", "The Vim Monk"],
            ].map(([title, desc, c, span, big]) => (
              <BentoGridItem key={title} title={title} description={desc} className={`${span} border-white/10 bg-white/5 text-white`}
                header={<div className="flex h-full min-h-16 items-end rounded-lg p-3 text-3xl font-bold" style={{ background: `linear-gradient(135deg, ${c}55, transparent)`, color: c }}>{big}</div>} />
            ))}
          </BentoGrid>
        </div>
      </section>

      {/* 05 — the share card */}
      <section className="slide grid items-center gap-8 bg-[#12031f] px-6 md:grid-cols-2">
        <div className="mx-auto max-w-md">
          <Kicker>That's a wrap</Kicker>
          <h2 className="mt-3 text-5xl font-bold tracking-tight">It ends on a card made for posting.</h2>
          <p className="mt-4 text-white/70">Saved as PNG and SVG in ~/Pictures. Tilt it.</p>
        </div>
        <CardContainer containerClassName="py-0">
          <CardBody className="h-auto w-[min(80vw,22rem)]">
            <CardItem translateZ={80} className="w-full">
              <img src="./card.png" alt="An example Terminal Wrapped share card" className="w-full rounded-2xl shadow-2xl shadow-[#ff5fd2]/30" />
            </CardItem>
          </CardBody>
        </CardContainer>
      </section>

      {/* 06 — install */}
      <section id="install" className="slide flex flex-col items-center justify-center gap-8 bg-[#0b0214] px-6">
        <Kicker>Unwrap yours</Kicker>
        <Terminal className="w-full max-w-2xl border-white/10 bg-black/60 text-white">
          <TypingAnimation className="break-all">{`$ ${INSTALL}`}</TypingAnimation>
          <AnimatedSpan className="text-[#b6ff5c]">✓ Arch Linux, Python 3.13</AnimatedSpan>
          <AnimatedSpan className="text-[#b6ff5c]">✓ installed to ~/.local/bin/termwrapped</AnimatedSpan>
          <AnimatedSpan className="text-[#ff5fd2]">Unwrap your year:  termwrapped</AnimatedSpan>
        </Terminal>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <RainbowButton onClick={() => navigator.clipboard?.writeText(INSTALL)}>Copy install command</RainbowButton>
          <a href={REPO} className="mono text-sm underline underline-offset-4 text-white/70 hover:text-white">github.com/ethembeldagli/termwrapped →</a>
        </div>
        <p className="mono text-xs text-white/50">Any distro · bash, zsh, fish · Python 3.9+ · nothing leaves your machine</p>
      </section>

      <div className="snap-end"><Footer mode="dark" /></div>
    </main>
  )
}
