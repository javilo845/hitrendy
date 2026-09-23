import type { ComponentProps } from "react";
import Image from "next/image";

type Props = Omit<ComponentProps<"span">, "children"> & {
  inverse?: boolean;
};

export function Logo({ inverse = false, className = "", ...props }: Props) {
  return (
    <span
      {...props}
      className={`logo ${inverse ? "logo--inverse" : ""} ${className}`.trim()}
    >
      <Image
        src="/brand/hitrendy-mark.svg"
        alt=""
        aria-hidden="true"
        width={32}
        height={32}
      />
      <strong>HiTrendy</strong>
    </span>
  );
}
