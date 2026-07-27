import { useEffect, useState } from "react";
import type { JSX } from "react";
import { BrandMark } from "../components/Brand";

export default function PublicHome(): JSX.Element {
  const reduced =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [run, setRun] = useState(0);
  const [finished, setFinished] = useState(reduced);

  useEffect(() => {
    if (reduced) {
      setFinished(true);
      return;
    }
    setFinished(false);
    const timer = window.setTimeout(() => setFinished(true), 7200);
    return () => window.clearTimeout(timer);
  }, [reduced, run]);

  useEffect(() => {
    const skip = (event: KeyboardEvent): void => {
      if (!finished && (event.key === "Enter" || event.key === " " || event.key === "Escape")) {
        event.preventDefault();
        setFinished(true);
      }
    };
    window.addEventListener("keydown", skip);
    return () => window.removeEventListener("keydown", skip);
  }, [finished]);

  const replay = (): void => {
    if (reduced) return;
    setFinished(false);
    setRun(value => value + 1);
  };

  return (
    <main className={`public-home ${finished ? "motion-finished" : ""}`}>
      <section
        key={run}
        className="seed-motion"
        aria-label="笛语品牌动效"
        onClick={() => setFinished(true)}
      >
        <svg className="seed-story" viewBox="0 0 420 260" aria-hidden="true">
          <path
            className="seed-path uncertain"
            d="M72 146 C108 112 126 184 164 135 C194 98 180 72 224 90 C252 102 250 145 214 157 C184 166 166 125 194 111"
          />
          <path className="seed-path branch" d="M164 135 C148 104 151 82 132 68" />
          <path className="seed-path return" d="M164 135 C196 178 237 177 270 146" />
          <circle className="seed-dot origin" cx="72" cy="146" r="7" />
          <path className="direction-turn" d="M210 63 L232 103 L188 103 Z" />
          <circle className="rhythm rhythm-one" cx="210" cy="132" r="7" />
          <circle className="rhythm rhythm-two" cx="210" cy="160" r="7" />
          <circle className="rhythm rhythm-three" cx="210" cy="188" r="7" />
        </svg>
        <div className="motion-final">
          <img src="/assets/diyu-logo-primary.svg" alt="笛语 DIYU AGENT" />
        </div>
        {!finished && (
          <button
            className="motion-skip"
            type="button"
            onClick={event => {
              event.stopPropagation();
              setFinished(true);
            }}
          >
            跳过
          </button>
        )}
      </section>

      <section className="home-message" aria-hidden={!finished}>
        <BrandMark />
        <h1>把一句想法，变成真正属于品牌的表达。</h1>
        <a className="button primary" href="/login">
          开始创作
        </a>
        <nav className="quiet-entry-links" aria-label="其他独立入口">
          <a href="/tenant-admin/login">品牌管理</a>
          <a href="/ops/login">笛语运维</a>
          {!reduced && (
            <button type="button" onClick={replay}>
              重播动效
            </button>
          )}
        </nav>
      </section>
    </main>
  );
}
