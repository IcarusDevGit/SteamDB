# Historical Rating Labels Specification

## Purpose

Defines how cumulative historical Steam review counts become stable weekly rating labels alongside the existing numeric positive-review ratio.

## Requirements

### Requirement: Historical review aggregate
The system SHALL aggregate positive and negative Steam histogram reviews occurring before the Tuesday immediately following the selected chart week, and SHALL derive both the numeric rating and rating label from that same aggregate.

#### Scenario: Reviews occur after the closed week
- **WHEN** histogram data contains reviews at or after the following Tuesday at 00:00 UTC
- **THEN** those reviews affect neither the historical numeric rating nor its label

#### Scenario: Historical aggregate is available
- **WHEN** at least one eligible review exists before the cutoff
- **THEN** the numeric rating equals eligible positive reviews divided by all eligible reviews
- **AND** label classification uses that same positive count and total count

### Requirement: Rating label thresholds
The system SHALL classify an aggregate using its exact positive-review ratio and total review count. For 500 or more reviews it SHALL assign `Overwhelmingly Positive` at 95–100%, `Very Positive` at 80–94%, `Mostly Positive` at 70–79%, `Mixed` at 40–69%, `Mostly Negative` at 20–39%, and `Overwhelmingly Negative` at 0–19%. For 50–499 reviews it SHALL assign `Very Positive` at 80–100%, `Mostly Positive` at 70–79%, `Mixed` at 40–69%, `Mostly Negative` at 20–39%, and `Very Negative` at 0–19%. For 10–49 reviews it SHALL assign `Positive` at 80–100%, `Mostly Positive` at 70–79%, `Mixed` at 40–69%, `Mostly Negative` at 20–39%, and `Negative` at 0–19%.

#### Scenario: Positive threshold boundary
- **WHEN** an aggregate has exactly 500 reviews and an exact positive ratio of 95%
- **THEN** its label is `Overwhelmingly Positive`

#### Scenario: Review-count boundary changes the label
- **WHEN** two aggregates have the same exact 90% positive ratio but totals of 49 and 50 reviews
- **THEN** their labels are respectively `Positive` and `Very Positive`

#### Scenario: Negative review-count boundary
- **WHEN** aggregates have an exact positive ratio below 20% and totals of 49, 50, and 500 reviews
- **THEN** their labels are respectively `Negative`, `Very Negative`, and `Overwhelmingly Negative`

### Requirement: Insufficient reviews have an explicit label
The system SHALL assign `no_label` when fewer than 10 eligible reviews exist, including when no eligible reviews exist. A null rating label SHALL exclusively indicate that label collection has not completed successfully for that weekly row.

#### Scenario: Fewer than ten reviews
- **WHEN** the historical aggregate contains between zero and nine total reviews
- **THEN** its rating label is `no_label`

#### Scenario: Label has not been collected
- **WHEN** a weekly row has not yet been processed successfully for rating-label collection
- **THEN** its rating label remains null rather than `no_label`
