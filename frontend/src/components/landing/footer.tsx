import { Container } from "@/components/ui/container";
import { BrandMark } from "@/components/ui/brand-mark";

type FooterLink = { href: string; label: string };

function FooterCol({ title, links }: { title: string; links: FooterLink[] }) {
  return (
    <div>
      <h4 className="mb-3.5 font-mono text-[12px] uppercase tracking-[0.08em] text-faint">
        {title}
      </h4>
      {links.map((link) => (
        <a
          key={link.label}
          href={link.href}
          className="mb-2.5 block text-sm text-ink-soft hover:text-ink"
        >
          {link.label}
        </a>
      ))}
    </div>
  );
}

const PRODUCT_LINKS: FooterLink[] = [
  { href: "#how", label: "How it works" },
  { href: "#product", label: "Features" },
  { href: "#faq", label: "FAQ" },
];

export function Footer() {
  return (
    <footer className="mt-[30px] border-t border-line pt-[54px] pb-10">
      <Container>
        <div className="mb-9 grid grid-cols-2 gap-[30px] md:grid-cols-[2fr_1fr]">
          <div>
            <div className="mb-3 flex items-center gap-[9px]">
              <BrandMark size={22} />
              <span className="text-[17px] font-semibold tracking-[-0.01em]">
                Intervyn
              </span>
            </div>
            <p className="max-w-[280px] text-sm text-muted">
              The open-source AI voice interviewer. Practice out loud, in any
              language.
            </p>
          </div>
          <FooterCol title="Product" links={PRODUCT_LINKS} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-line pt-[22px] text-[13px] text-faint">
          <span>© 2026 Intervyn · MIT License</span>
          <span className="font-mono">Built in the open</span>
        </div>
      </Container>
    </footer>
  );
}
