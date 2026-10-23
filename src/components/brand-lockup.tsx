import Image from "next/image";
import Link from "next/link";

export function BrandLockup() {
  return (
    <Link className="brand-lockup" href="/" aria-label="Plus11 home">
      <Image src="/plus11-mark.svg" alt="" width={38} height={38} priority />
      <span className="brand-word">Plus<span>11</span></span>
    </Link>
  );
}
