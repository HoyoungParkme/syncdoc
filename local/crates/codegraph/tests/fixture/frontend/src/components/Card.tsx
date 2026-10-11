/** 공용 카드 — 화면 ID가 없다 */
import { joinPath } from "../api/client";

export function Card({ title }: { title: string }) {
  const onClick = () => {
    joinPath("a", title);
  };
  return <div onClick={onClick}>{title}</div>;
}

const helper = (x: number) =>
  x + 1;

export class Box {
  open() {
    return helper(1);
  }
}
