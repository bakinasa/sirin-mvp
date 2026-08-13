import clsx from "clsx";
import { STATUS_LABELS, statusColor } from "../lib/api";

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx("badge", statusColor(status))}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}
