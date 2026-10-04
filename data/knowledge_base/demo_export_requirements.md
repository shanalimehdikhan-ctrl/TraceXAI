# TraceX Demo Export Knowledge Base

## Product Traceability
A product traceability record should connect:
Supplier -> Material -> Product -> Supporting Evidence.

Typical evidence may include:
- Supplier identity record
- Material declaration
- Product identifier
- Manufacturing or batch reference
- Quality or test record

A missing link should be marked as incomplete or unclear.
The system must not invent missing evidence.

## Supplier Evidence
Supplier identity should be supported by a supplied registration
or supplier-identification record.

If supplier evidence is absent:
Status = MISSING

If supplier information exists but supporting evidence is insufficient:
Status = UNCLEAR

## Material Evidence
Material composition should be linked to a supplied declaration,
certificate, or equivalent evidence.

Material composition and material origin are separate pieces of evidence.

## Product Identification
A finished product should have a product identifier.

Where available, batch or production references should be linked
to the product.

Missing batch information should be identified as a traceability gap.

## Evidence Verification
Evidence status:

VERIFIED
The claim is explicitly supported by supplied evidence.

MISSING
Expected evidence has not been supplied.

UNCLEAR
Information exists but is insufficient to verify the claim.

The AI must never fabricate evidence.

## Compliance Decision
Compliance decisions should be based on retrieved knowledge and
supplied evidence.

When the knowledge base does not contain sufficient information,
the system should return:

"Insufficient evidence — human review required."

## Risk Handling
Important gaps should be surfaced clearly.

Examples:
- Missing supplier evidence
- Missing material evidence
- Missing product identification
- Missing testing evidence
- Broken traceability link

Every risk finding should state the evidence gap that caused it.

## Human Review
TraceX AI is a decision-support system.

When evidence is contradictory, incomplete, or outside the knowledge
base, the system should request human review instead of inventing
a conclusion.