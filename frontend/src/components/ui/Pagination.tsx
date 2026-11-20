import { ChevronLeft, ChevronRight } from "lucide-react";
import "./ui.css";

export default function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <div className="ui-pagination">
      <span>
        Showing {first}–{last} of {total}
      </span>
      <div className="ui-pagination-controls">
        <button
          type="button"
          className="ui-btn ui-btn-secondary ui-btn-sm"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
        >
          <ChevronLeft size={14} /> Previous
        </button>
        <span>
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          className="ui-btn ui-btn-secondary ui-btn-sm"
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages}
        >
          Next <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
