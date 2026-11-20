## MODIFIED Requirements

### Requirement: Multi-Tuesday extraction
The system SHALL accept an optional start Tuesday and optional end Tuesday for an extraction run. When neither date is supplied, the system SHALL select the last closed Tuesday. When only the start date is supplied, the system SHALL collect that single weekly dataset. When both dates are supplied, the system SHALL collect every Tuesday from the start date through the end date, inclusive.

#### Scenario: No dates supplied
- **WHEN** an operator starts extraction without a start date or end date
- **THEN** the system collects the weekly dataset for the last closed Tuesday

#### Scenario: Start date supplied without end date
- **WHEN** an operator starts extraction with a valid start Tuesday and no end date
- **THEN** the system collects only the weekly dataset for the start date

#### Scenario: Multiple valid Tuesdays
- **WHEN** an operator starts extraction with valid start and end Tuesdays and the end follows the start
- **THEN** the system collects a distinct weekly dataset for every Tuesday from the start date through the end date, including both boundaries

#### Scenario: Equal range boundaries
- **WHEN** an operator supplies the same valid Tuesday as both the start date and end date
- **THEN** the system collects that weekly dataset once

#### Scenario: Invalid weekly date
- **WHEN** an operator supplies a start date or end date that is malformed or is not a Tuesday
- **THEN** the system rejects the invocation with a clear validation error before collecting data

#### Scenario: Reversed date range
- **WHEN** an operator supplies an end Tuesday earlier than the start Tuesday
- **THEN** the system rejects the range with a clear validation error before collecting data
