import { useState, type ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Inbox,
  RefreshCw,
  Search,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

/**
 * Umumiy jadval: sortlash (ustun sarlavhasini bosish), qidiruv (searchPlaceholder
 * berilsa), sahifalash (qatorlar pageSize dan oshsa), yuklanish skeleti, bo'sh
 * holat va xato+qayta urinish holatlari.
 */
export default function DataTable<TData>({
  columns,
  data,
  isLoading = false,
  error = null,
  onRetry,
  searchPlaceholder,
  empty,
  pageSize = 50,
  onRowClick,
  footer,
}: {
  columns: ColumnDef<TData, any>[];
  data: TData[] | undefined;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  searchPlaceholder?: string; // berilmasa qidiruv maydoni chiqmaydi
  empty?: { icon?: LucideIcon; text: string; action?: ReactNode };
  pageSize?: number;
  onRowClick?: (row: TData) => void;
  footer?: ReactNode; // jadval ostidagi ixtiyoriy jami-qator va h.k.
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  const table = useReactTable({
    data: data ?? [],
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    globalFilterFn: "includesString",
    initialState: { pagination: { pageSize } },
  });

  // ─── Xato holati ───
  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-10 text-center">
        <AlertCircle className="h-8 w-8 text-rose-400" />
        <p className="text-sm text-rose-700">{error}</p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Qayta urinish
          </Button>
        )}
      </div>
    );
  }

  const rows = table.getRowModel().rows;
  const totalFiltered = table.getFilteredRowModel().rows.length;
  const showPagination = totalFiltered > pageSize;
  const EmptyIcon = empty?.icon ?? Inbox;

  return (
    <div className="space-y-2">
      {searchPlaceholder && (
        <div className="relative max-w-xs">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            placeholder={searchPlaceholder}
            className="pl-8"
          />
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((header) => {
                  const canSort = header.column.getCanSort();
                  const dir = header.column.getIsSorted();
                  return (
                    <TableHead key={header.id} className="whitespace-nowrap">
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          className="inline-flex items-center gap-1 hover:text-slate-900"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {dir === "asc" ? (
                            <ArrowUp className="h-3.5 w-3.5" />
                          ) : dir === "desc" ? (
                            <ArrowDown className="h-3.5 w-3.5" />
                          ) : (
                            <ArrowUpDown className="h-3.5 w-3.5 text-slate-300" />
                          )}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {columns.map((_, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-[160px]" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length}>
                  <div className="flex flex-col items-center gap-2 py-10 text-center">
                    <EmptyIcon className="h-8 w-8 text-slate-300" />
                    <p className="text-sm text-slate-500">
                      {globalFilter
                        ? "Qidiruv bo'yicha hech narsa topilmadi."
                        : (empty?.text ?? "Ma'lumot yo'q.")}
                    </p>
                    {!globalFilter && empty?.action}
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={cn(onRowClick && "cursor-pointer")}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        {footer}
      </div>

      {showPagination && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            {totalFiltered} ta yozuv · {table.getState().pagination.pageIndex + 1} /{" "}
            {table.getPageCount()} sahifa
          </span>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={!table.getCanPreviousPage()}
              onClick={() => table.previousPage()}
            >
              <ChevronLeft className="h-4 w-4" />
              Oldingi
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!table.getCanNextPage()}
              onClick={() => table.nextPage()}
            >
              Keyingi
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
