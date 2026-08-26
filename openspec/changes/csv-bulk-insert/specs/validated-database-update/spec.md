## ADDED Requirements

### Requirement: Bounded bulk persistence
The approved CSV workflow SHALL consolidate repeated tag references into one candidate per tag identifier before mutation and SHALL persist tag candidates, game candidates, rank displacement, and weekly records using a bounded number of database commands that does not grow with the number of CSV rows or tag references.

#### Scenario: Repeated tag references agree
- **WHEN** multiple validated CSV records associate the same tag identifier with the same canonical name
- **THEN** the workflow prepares that tag identifier once for persistence and preserves every game's association with it

#### Scenario: Repeated tag references conflict
- **WHEN** validated CSV records associate the same tag identifier with different names
- **THEN** the workflow rejects the application before database mutation and identifies the contradictory tag mapping

#### Scenario: Approved file contains a complete weekly chart
- **WHEN** the operator applies an approved 100-record weekly CSV containing any number of repeated tag references
- **THEN** the workflow persists each entity set in bulk without issuing one database command per tag reference or per game record

#### Scenario: Bulk persistence succeeds
- **WHEN** every bulk catalog and weekly-record operation succeeds
- **THEN** the workflow produces the same catalog and weeksheet state required by insert-only catalog handling and weekly reconciliation

