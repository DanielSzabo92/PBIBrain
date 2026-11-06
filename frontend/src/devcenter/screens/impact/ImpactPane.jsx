// Impact item pane (UI design 4.5): status, h2 name, full reason, blocking sentence, shortest path,
// "Show other paths", Cause link, Certainty, Policy, and the actions with one line each.
// Cascade and Repoint take their input in the removal policy dialog; Map to target takes it here.
import React, { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import { SidePane } from "@/components/ui/side-pane";
import { StatusBadge } from "@/components/ui/status-badge";
import { t } from "../../copy.js";
import PathStepList from "../../components/PathStepList.jsx";
import { POLICY_ACTIONS, STATUS_TONE, actionLabel, itemStatus, statusLabel } from "./impactModel.js";

const HELP = {
  include_in_rewrite: "impact.action.include.help",
  add_from_donor: "impact.action.add_from_donor.help",
  map_to_target: "impact.action.map.help",
  drop_added_object: "impact.action.drop_added.help",
  remove_field: "impact.action.remove_field.help",
};

export default function ImpactPane({ item, http, policy, disabled, reasonId, pendingAction, actionError, mapFocusSeq, returnFocusRef, onClose, onAction, onPolicy, onCause }) {
  const [paths, setPaths] = useState({ status: "idle", list: [] });
  const [mapTarget, setMapTarget] = useState("");
  const policyRef = useRef(null);

  useEffect(() => {
    setPaths({ status: "idle", list: [] });
    setMapTarget("");
  }, [item?.id]);

  useEffect(() => {
    if (mapFocusSeq) document.getElementById("dc-impact-map")?.focus();
  }, [mapFocusSeq]);

  if (!item) return null;
  const status = itemStatus(item);
  const allowed = item.allowed_actions ?? [];
  const hasPolicy = allowed.some((action) => POLICY_ACTIONS.has(action));
  const plainActions = allowed.filter((action) => !POLICY_ACTIONS.has(action) && action !== "map_to_target");
  const causeName = item.path?.[0]?.name ?? item.cause;

  const loadPaths = async () => {
    setPaths({ status: "loading", list: [] });
    try {
      const reply = await http.getImpactPaths(item.id, { limit: 50 });
      setPaths({ status: "ready", list: (reply.paths ?? []).slice(1) });
    } catch {
      setPaths({ status: "error", list: [] });
    }
  };

  return (
    <SidePane open title={item.impacted_object?.name ?? item.id} onClose={onClose} returnFocusRef={returnFocusRef} className="dc-impact-pane" busy={Boolean(pendingAction)}>
      <div className="dc-impact-pane-body" data-item-id={item.id}>
        <StatusBadge tone={STATUS_TONE[status]} label={statusLabel(status)} />
        <section aria-label={t("impact.pane.reason")}>
          <p className="dc-impact-pane-reason">{item.reason_text}</p>
          {status === "blocking" ? <p className="dc-impact-pane-blocking">{t("impact.pane.blocking")}</p> : null}
        </section>
        <section>
          <h3 className="dc-impact-pane-h3">{t("impact.pane.path")}</h3>
          <PathStepList steps={item.path ?? []} label={t("impact.pane.path")} />
          {(item.other_paths_count ?? 0) > 0 ? (
            paths.status === "ready" ? (
              <div className="dc-impact-pane-paths">
                <h3 className="dc-impact-pane-h3">{t("impact.pane.other_paths")}</h3>
                {paths.list.map((steps, index) => <PathStepList key={index} steps={steps} label={`${t("impact.pane.other_paths")} ${index + 1}`} />)}
              </div>
            ) : (
              <Button variant="outline" size="sm" loading={paths.status === "loading"} loadingText={t("impact.paths.loading")} onClick={loadPaths}>
                {t("impact.other_paths.action")}
              </Button>
            )
          ) : null}
          {paths.status === "error" ? <Notice tone="bad">{t("impact.paths.fail")}</Notice> : null}
        </section>
        <dl className="dc-impact-pane-facts">
          <dt>{t("impact.pane.cause")}</dt>
          <dd><Button variant="link" size="sm" className="dc-impact-cause" onClick={() => onCause(item)}>{causeName}</Button></dd>
          <dt>{t("impact.pane.certainty")}</dt>
          <dd>{t(`impact.certainty.${item.certainty}`)}</dd>
          {hasPolicy ? (
            <>
              <dt>{t("impact.pane.policy")}</dt>
              <dd>{policy ? t(`impact.policy.${policy}`) : t("shared.not_known")}</dd>
            </>
          ) : null}
        </dl>
        <section className="dc-impact-pane-actions">
          <h3 className="dc-impact-pane-h3">{t("impact.pane.actions")}</h3>
          {!allowed.length ? <p className="dc-impact-pane-line">{t("impact.pane.no_actions")}</p> : null}
          {hasPolicy ? (
            <div className="dc-impact-pane-action">
              <Button ref={policyRef} variant="outline" size="sm" disabled={disabled} aria-describedby={disabled ? reasonId : undefined} onClick={() => onPolicy(item, null, policyRef.current)}>
                {t("row.removal.block.action")}
              </Button>
              <p className="dc-impact-pane-line">{t("impact.action.policy.help")}</p>
            </div>
          ) : null}
          {allowed.includes("map_to_target") ? (
            <div className="dc-impact-pane-action">
              <label className="ui-field-label" htmlFor="dc-impact-map">{t("impact.pane.map.label")}</label>
              <Input id="dc-impact-map" value={mapTarget} disabled={disabled} aria-describedby="dc-impact-map-hint" onChange={(event) => setMapTarget(event.target.value)} />
              <p id="dc-impact-map-hint" className="dc-impact-pane-line">{t("impact.pane.map.hint")}</p>
              <Button
                variant="outline"
                size="sm"
                disabled={disabled || !mapTarget.trim()}
                loading={pendingAction === "map_to_target"}
                loadingText={t("shared.updating")}
                onClick={(event) => onAction(item, "map_to_target", event.currentTarget, { target_object: mapTarget.trim() })}>
                {actionLabel("map_to_target")}
              </Button>
              <p className="dc-impact-pane-line">{t(HELP.map_to_target)}</p>
            </div>
          ) : null}
          {plainActions.map((action) => (
            <div key={action} className="dc-impact-pane-action">
              <Button
                variant="outline"
                size="sm"
                disabled={disabled}
                aria-describedby={disabled ? reasonId : undefined}
                loading={pendingAction === action}
                loadingText={t("shared.updating")}
                onClick={(event) => onAction(item, action, event.currentTarget)}>
                {actionLabel(action)}
              </Button>
              <p className="dc-impact-pane-line">{t(HELP[action])}</p>
            </div>
          ))}
          {actionError ? <Notice tone="bad" role="alert">{t("impact.action.fail")}</Notice> : null}
        </section>
      </div>
    </SidePane>
  );
}
