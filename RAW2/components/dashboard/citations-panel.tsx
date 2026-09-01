import { Badge } from "@/components/ui/badge"
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverTitle,
  PopoverDescription,
} from "@/components/ui/popover"
import { Empty, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { FileTextIcon } from "lucide-react"
import type { Citation } from "@/lib/mock-data"

export function CitationsPanel({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-4">
        <Empty className="p-0">
          <EmptyTitle>No sources yet</EmptyTitle>
          <EmptyDescription>Citations will appear once agents report findings.</EmptyDescription>
        </Empty>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs font-medium text-muted-foreground">Sources</p>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((citation) => (
          <Popover key={citation.title}>
            <PopoverTrigger
              render={
                <button type="button">
                  <Badge variant="secondary" className="cursor-pointer gap-1">
                    <FileTextIcon />
                    {citation.label}
                  </Badge>
                </button>
              }
            />
            <PopoverContent className="w-64">
              <PopoverTitle>{citation.title}</PopoverTitle>
              <PopoverDescription>{citation.summary}</PopoverDescription>
              <p className="text-[11px] text-muted-foreground">Source: {citation.source}</p>
            </PopoverContent>
          </Popover>
        ))}
      </div>
    </div>
  )
}
