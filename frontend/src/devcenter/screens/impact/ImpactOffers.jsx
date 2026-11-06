// Impact Offers view (UI design 4.5): a tree by donor report, page, visual and filter.
// The page checkbox has the mixed state. Each change calls offer_select. Bookmarks are "Information only".
// Selected visuals that need missing fields add Needs and a banner with "Open Needs".
import React from "react";
import { Bookmark } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Banner } from "@/components/ui/notice";
import { EmptyState } from "@/components/ui/result-panel";
import { t, tn } from "../../copy.js";
import { missingFieldCount, offerLine, offerTree, pageCheckState } from "./impactModel.js";

export default function ImpactOffers({ offers, disabled, reasonId, onToggle, onTogglePage, onOpenNeeds }) {
  const tree = offerTree(offers);
  const missing = missingFieldCount(offers);
  if (!offers?.length) return <EmptyState headingLevel={2} title={t("impact.empty.offers")} />;
  return (
    <div className="dc-offers">
      <p className="dc-offers-help">{t("impact.offers.help")}</p>
      {missing > 0 ? (
        <Banner tone="warn" data-banner="offer-needs" actions={<Button variant="outline" size="sm" onClick={onOpenNeeds}>{t("impact.offers.fields.action")}</Button>}>
          {tn("impact.offers.fields", missing)}
        </Banner>
      ) : null}
      {tree.map((donor) => (
        <section key={donor.sourceId} className="dc-offers-donor" aria-labelledby={`dc-offers-${donor.sourceId}`}>
          <h2 id={`dc-offers-${donor.sourceId}`} className="dc-offers-donor-title">{donor.sourceName}</h2>
          <ul className="dc-offers-tree">
            {donor.pages.map((page) => {
              const state = pageCheckState(page.items);
              return (
                <li key={page.name} className="dc-offers-page">
                  <div className="dc-offers-line">
                    <Checkbox
                      size="target"
                      checked={state}
                      disabled={disabled}
                      aria-describedby={disabled ? reasonId : undefined}
                      aria-label={t("impact.offers.page.select", { page: page.name })}
                      onCheckedChange={() => onTogglePage(page.items, state !== true)}
                    />
                    <span className="dc-offers-page-name">{t("impact.offers.page", { page: page.name })}</span>
                  </div>
                  <ul className="dc-offers-items">
                    {page.items.map((offer) => (
                      <li key={offer.id} className="dc-offers-line" data-offer-id={offer.id}>
                        <Checkbox
                          size="target"
                          checked={Boolean(offer.selected)}
                          disabled={disabled}
                          aria-describedby={disabled ? reasonId : undefined}
                          aria-label={offer.name}
                          onCheckedChange={(checked) => onToggle(offer, checked === true)}
                        />
                        <span className="dc-offers-name">{offer.name}</span>
                        <span className="dc-offers-kind">{offerLine(offer)}</span>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
            {donor.bookmarks.map((offer) => (
              <li key={offer.id} className="dc-offers-line dc-offers-bookmark" data-offer-id={offer.id}>
                <Bookmark aria-hidden="true" />
                <span className="dc-offers-name">{offer.name}</span>
                <span className="dc-impact-tag">{t("impact.tag.information")}</span>
                <span className="dc-offers-kind">{t("impact.offers.bookmarks")}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
