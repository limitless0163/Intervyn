"use client";

import Image from "next/image";
import { Container } from "@/components/ui/container";
import { useMessages } from "@/hooks/use-i18n";
import { t } from "@/lib/i18n";

const COMPANIES = [
  { name: "ByteDance", file: "bytedance" },
  { name: "Tencent", file: "tencent" },
  { name: "Alibaba", file: "alibaba" },
  { name: "Baidu", file: "baidu" },
  { name: "Meituan", file: "meituan" },
  { name: "JD", file: "jd" },
];

export function LogoCloud() {
  const messages = useMessages();
  return (
    <div className="landing-companies">
      <Container className="landing-container">
        <p className="mb-5 text-center text-[15px] text-muted sm:text-base">
          {t(messages, "landing.logoCloud")}
        </p>
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {COMPANIES.map(({ name, file }) => (
            <div key={file} className="landing-company">
              <div className="landing-company-logo">
                <Image
                  src={`/logos/companies/${file}.png`}
                  alt={`${name} logo`}
                  width={120}
                  height={40}
                  className={`landing-company-image landing-company-image-${file}`}
                />
              </div>
              <span>{name}</span>
            </div>
          ))}
        </div>
      </Container>
    </div>
  );
}
