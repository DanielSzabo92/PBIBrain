import * as React from "react";
import { useState, useEffect } from "react";
import { Check, X, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Menu } from "./ui/menu";
import { readableText } from "../presentation";

export default function ReviewDecision({
  item,
  onReview,
  onDecide,
  disabled = false,
  isEditing = false,
  onStartEdit,
  onCancelEdit,
  compact = true,
  iconOnly = false,
}) {
  const initialValue = readableText(item?.value ?? item?.meaning ?? item?.properties?.value ?? "");
  const [draft, setDraft] = useState(initialValue);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(initialValue);
  }, [initialValue, isEditing]);

  const handleDecide = async (action, valueOverride = undefined) => {
    if (busy || disabled) return;
    setError("");
    setBusy(true);
    try {
      if (onDecide) {
        await onDecide(action, item, valueOverride);
      } else if (onReview) {
        const ok = await onReview(action, item, valueOverride);
        if (!ok) setError("Could not save decision. Try again.");
      }
    } catch {
      setError("Could not save decision. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const handleSave = async () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    const action = item.status === "candidate" ? "override" : "edit";
    await handleDecide(action, trimmed);
    if (onCancelEdit) onCancelEdit();
  };

  const handleKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (onCancelEdit) onCancelEdit();
    } else if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSave();
    }
  };

  if (isEditing) {
    return (
      <div className="review-edit-row" onKeyDown={handleKeyDown}>
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Enter meaning…"
          aria-label="Edit meaning"
          className="review-edit-input"
          disabled={busy}
        />
        <Button
          variant="default"
          size="sm"
          className="save-meaning-button"
          disabled={!draft.trim() || busy}
          onClick={handleSave}
        >
          Save meaning
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="cancel-edit-button"
          disabled={busy}
          onClick={onCancelEdit}
        >
          Cancel
        </Button>
      </div>
    );
  }

  const isStale = item?.issue === "stale" || item?.issue_type === "stale" || item?.status === "stale";

  if (isStale) {
    return (
      <div className="review-actions" data-ui-actions="">
        <Button
          variant="destructive"
          size="sm"
          className="remove-decision-button"
          disabled={busy || disabled}
          onClick={() => handleDecide("remove")}
        >
          Remove decision
        </Button>
      </div>
    );
  }

  const overflowGroups = [
    {
      items: [
        {
          label: "Change meaning…",
          icon: Pencil,
          onSelect: () => onStartEdit && onStartEdit(item),
        },
      ],
    },
  ];

  return (
    <div className="review-actions" data-ui-actions="">
      <Button
        variant="default"
        size={iconOnly ? "icon-sm" : "sm"}
        className="approve-button"
        aria-label={iconOnly ? "Approve" : undefined}
        title={iconOnly ? "Approve (A)" : undefined}
        disabled={busy || disabled}
        onClick={() => handleDecide("approve")}
      >
        <Check className="size-4" aria-hidden="true" />
        {iconOnly ? null : "Approve"}
      </Button>
      <Button
        variant="ghost"
        size={iconOnly ? "icon-sm" : "sm"}
        className="reject-button"
        aria-label={iconOnly ? "Reject" : undefined}
        title={iconOnly ? "Reject (R)" : undefined}
        disabled={busy || disabled}
        onClick={() => handleDecide("reject")}
      >
        <X className="size-4" aria-hidden="true" />
        {iconOnly ? null : "Reject"}
      </Button>
      <Menu
        label="More actions"
        align="end"
        groups={overflowGroups}
        trigger={
          <Button
            variant="ghost"
            size="icon-sm"
            className="overflow-button"
            aria-label="More review actions"
            disabled={busy || disabled}
          >
            <MoreHorizontal className="size-4" aria-hidden="true" />
          </Button>
        }
      />
      {error ? <p className="review-decision-error" role="alert">{error}</p> : null}
    </div>
  );
}
