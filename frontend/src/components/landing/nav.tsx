"use client";

import Link from "next/link";
import { BrandMark } from "@/components/ui/brand-mark";
import { MobileMenu } from "@/components/landing/mobile-menu";
import { LandingLanguageMenu } from "@/components/landing/language-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function Nav() {
  const messages = useMessages();
  const links = [
    { href: "#product", label: t(messages, "landing.nav.product") },
    { href: "#how", label: t(messages, "landing.nav.how") },
    { href: "#github", label: t(messages, "landing.nav.github") },
    { href: "#faq", label: t(messages, "landing.nav.faq") },
  ];
  return (
    <nav className="landing-nav">
      <div className="landing-nav-inner">
        <div className="landing-nav-left">
          <a href="#top" className="landing-brand">
            <BrandMark size={20} />
            <span>Intervyn</span>
          </a>
          <div className="landing-nav-links">
            {links.map((link) => (
              <a key={link.href} href={link.href}>
                {link.label}
              </a>
            ))}
          </div>
        </div>
        <div className="landing-nav-actions">
          <ThemeToggle />
          <div className="landing-nav-desktop-actions">
            <LandingLanguageMenu />
            <Link href="/setup" className="landing-nav-start">
              {t(messages, "landing.nav.startShort")}
            </Link>
          </div>
          <MobileMenu
            links={[
              ...links,
              { href: "/setup", label: t(messages, "landing.nav.startShort") },
            ]}
            showLanguageToggle
          />
        </div>
      </div>
    </nav>
  );
}
