/**
 * TE sample-10 program-feed contract.
 *
 * Source: `data/te-sample-10/activity/program-feed.json`
 * Shape verified from real files.
 *
 * Events are a discriminated union over `kind`. New kinds may appear in future
 * vintages — the rendering layer should handle unknown kinds gracefully.
 */

export interface WalkFiredEvent {
  kind: "walk_fired";
  fired_at: string;
  recipe_id: string;
  recipe_label: string;
  tier: string;
  verdict: string;
  loco_auc: number;
  in_review_after: boolean;
  note: string;
}

export interface MethodologyAmendmentEvent {
  kind: "methodology_amendment";
  fired_at: string;
  title: string;
  detail: string;
  source?: string;
}

export interface VacateEvent {
  kind: "vacate";
  fired_at: string;
  recipe_id: string;
  recipe_label: string;
  prior_status: string;
  vacated_at: string;
  cause: string;
  note: string;
}

export interface IndicatorAddedEvent {
  kind: "indicator_added";
  fired_at: string;
  [key: string]: unknown;
}

export interface DataSyncEvent {
  kind: "data_sync";
  fired_at: string;
  [key: string]: unknown;
}

export interface GraduationEvent {
  kind: "graduation";
  fired_at: string;
  recipe_id: string;
  recipe_label: string;
  [key: string]: unknown;
}

export interface GenericEvent {
  kind: string;
  fired_at: string;
  [key: string]: unknown;
}

export type ActivityEvent =
  | WalkFiredEvent
  | MethodologyAmendmentEvent
  | VacateEvent
  | IndicatorAddedEvent
  | DataSyncEvent
  | GraduationEvent
  | GenericEvent;

export interface ProgramFeed {
  vintage: string;
  events: ActivityEvent[];
  notes?: Record<string, string>;
}
