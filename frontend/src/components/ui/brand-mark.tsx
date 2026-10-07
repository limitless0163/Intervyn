import Image from "next/image";

/** The shared Intervyn mark used in navigation and app headers. */
export function BrandMark({
  size = 22,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <Image
      src="/logo.png"
      alt=""
      width={size}
      height={size}
      aria-hidden="true"
      className={className}
    />
  );
}
