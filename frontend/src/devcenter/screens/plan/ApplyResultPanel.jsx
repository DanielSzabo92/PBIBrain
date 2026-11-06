// Result panel of the Apply, format only, and Undo flows (UI design 5.5 step 4, 5.6, step U10).
// The parent focuses the title when the panel shows.
import React, { forwardRef } from "react";
import { CircleCheck, CircleX, TriangleAlert } from "lucide-react";
import { t } from "../../copy.js";

const ICONS = { ok: CircleCheck, warn: TriangleAlert, bad: CircleX };

const ApplyResultPanel = forwardRef(function ApplyResultPanel({ result, desktopAfter, children }, titleRef) {
  const Icon = ICONS[result.tone] || CircleCheck;
  return (
    <section className="dc-apply-result" data-result={result.type} data-tone={result.tone} aria-labelledby="dc-apply-result-title">
      <div className="dc-apply-result-head">
        <Icon className={`dc-apply-result-icon dc-tone-${result.tone}`} aria-hidden="true" />
        <h3 id="dc-apply-result-title" ref={titleRef} tabIndex={-1} className="dc-apply-result-title">{result.title}</h3>
      </div>
      {result.body ? <p className="dc-apply-result-body">{result.body}</p> : null}
      {result.type === "failure" && result.step ? <p className="dc-apply-result-step">{t("apply.fail.failed_step", { step: result.step })}</p> : null}
      {result.help ? <p className="dc-apply-result-help dc-muted">{result.help}</p> : null}
      {result.files?.length > 0 ? (
        <ul className="dc-apply-files">
          {result.files.map((file) => <li key={file} className="dc-mono">{file}</li>)}
        </ul>
      ) : null}
      {result.differences?.length > 0 ? (
        <table className="dc-table dc-apply-diff">
          <thead>
            <tr>
              <th scope="col">{t("apply.diff.object")}</th>
              <th scope="col">{t("apply.diff.expected")}</th>
              <th scope="col">{t("apply.diff.found")}</th>
            </tr>
          </thead>
          <tbody>
            {result.differences.map((item) => (
              <tr key={`${item.object}-${item.expected}`}>
                <td className="dc-mono">{item.object}</td>
                <td>{item.expected}</td>
                <td>{item.found}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {desktopAfter ? <p className="dc-apply-desktop" data-desktop="after">{desktopAfter}</p> : null}
      {children}
    </section>
  );
});

export default ApplyResultPanel;
