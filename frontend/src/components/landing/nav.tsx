"use client";

import Link from "next/link";
import { features } from "@intervyn/ee";
import { Container } from "@/components/ui/container";
import { buttonClasses } from "@/components/ui/button";
import { BrandMark } from "@/components/ui/brand-mark";
import { MobileMenu } from "@/components/landing/mobile-menu";
import { LanguageToggle } from "@/components/language-toggle";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

export function Nav() {
  const messages = useMessages();
  const links = [
    { href: "#how", label: t(messages, "landing.nav.how") },
    { href: "#product", label: t(messages, "landing.nav.product") },
    { href: "#oss", label: t(messages, "landing.nav.openSource") },
    { href: "#faq", label: t(messages, "landing.nav.faq") },
  ];
  return (
    <nav className="sticky top-0 z-50 border-b border-line bg-paper/80 backdrop-blur-md">
      <Container className="flex h-[66px] items-center justify-between gap-2 px-4 sm:px-7">
        <a href="#top" className="flex items-center gap-[9px]">
          <BrandMark size={22} />
          <span className="text-[17px] font-semibold tracking-[-0.01em]">
            Intervyn
          </span>
        </a>

        <div className="hidden gap-[30px] text-[14.5px] text-ink-soft min-[861px]:flex">
          {links.map((link) => (
            <a key={link.href} href={link.href} className="hover:text-ink">
              {link.label}
            </a>
          ))}
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3.5">
          <LanguageToggle className="hidden min-[861px]:inline-flex" />
          {features.auth ? (
            <Link
              href="/login"
              className="hidden text-[14.5px] text-ink-soft hover:text-ink min-[861px]:inline"
            >
              {t(messages, "landing.nav.signIn")}
            </Link>
          ) : null}
          <Link href="/setup" className={buttonClasses()}>
            {t(messages, "landing.nav.start")}
          </Link>
          <MobileMenu
            links={
              features.auth
                ? [
                    ...links,
                    {
                      href: "/login",
                      label: t(messages, "landing.nav.signIn"),
                    },
                  ]
                : links
            }
            showLanguageToggle
          />
        </div>
      </Container>
    </nav>
  );
}
