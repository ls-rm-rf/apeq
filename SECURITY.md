# Security scope of the research artifact

## V5 application and sequential requests

The release drivers implement private-file integer validation. Pair identifiers,
batch metadata and the equality vector delivered to the querier are permitted
leakage. Private candidate discovery, malicious input consistency and a deployed
business authorization layer are outside this prototype.

The V5 VOLE driver retains V4's session nonces and adds an explicit request domain
for sequences. Both bit-OT and VOLE regenerate their cryptographic setup for every
request. Warm experiments retain process and TCP transport together, so the
observed time difference cannot be attributed to transport alone. Sequential
ideal-resource bounds do not prove full software or concurrent UC security.

All-reply recovery claims apply to the explicitly modified interfaces, including
the stated affine-target bivariate family and its sampling/rank conditions.
They neither break the original OT-protected protocols nor prove that every
possible encoding requires OT. Historical details below remain relevant where
explicitly labeled V4 or historical.

This is the static semi-honest research implementation evaluated in the paper.
Correctness, transcript, sampling and interoperability tests do not certify
cryptographic security or establish a UC composition theorem for this software.

## IPS-OLE concrete strength

The measured parameters are `k=128, n=1024, rho=769, ell=255, t=48` over
`p=2^127-1`. The CSV field `security_param=128` records a nominal configuration,
not a certified 128-bit security level for the noisy Reed–Solomon backend.
The relevant IPS assumption is candidate-message indistinguishability.

The paper's candidate-message attack analysis considers guessing genuine positions
followed by Guruswami–Sudan list decoding. For 30 guessed positions and interpolation
multiplicity 20, the expected-trial exponent is 62.1124 and the
`n_prime^2 * multiplicity^4` interpolation proxy exponent per trial is 37.2019.
Their sum, 99.3144, is a cost-model result. It is neither a measured full attack
runtime nor a certified bit-security estimate. The proxy omits hidden constants,
root extraction, verification, memory and field-operation-to-machine conversion.
The search covers a particular attack family; it provides no security lower bound.

[Analysis sources](analysis/README.md) reproduce the counts and toy diagnostics.
V4 includes a classical bit-decomposition OT reference (`apeq_ot_eq.cpp`) and
new performance measurements. Its exact passive ideal-OT simulation removes the
noisy-code assumption, but the concrete base OT, IKNP and private generators still
carry their normal computational assumptions. This is a reference route, not a
certification of the historical packed parameters.

## Public-point sampling in V4

The packed benchmark now samples distinct field points using a private random
seed and transmits the actual vector, including its transport in setup. Zero is
allowed; the recipient validates counts and cross-set distinctness. With ideal
random coins this matches IPS's uniform sampling without replacement. Ordinary
private-generator security now supplies the corresponding computational hybrid.
The old public-seed constructor is retained solely for frozen-vector and historical
attack reproducibility; new network sessions use `PublicPoints::random` and the
explicit-point constructors. Fixing this interface does not prove code hardness.

## Ideal-model proofs and software composition

The equality reduction has perfect correctness and perfect privacy against static
semi-honest corruption in the ideal OLE hybrid. Privacy permits the querier's own
input and prior information, the **complete** equality-output vector and the
functionality's metadata. Correlated inputs can make one coordinate's equality bit
reveal information about another coordinate.

The composition corollary assumes an OLE backend that UC-realises the required
functionality in a compatible model. The measured software uses libOTe McRosRoy
base OT and IKNP extension. We have not established that this concrete software
composition meets all the corollary's assumptions, including setup, oracle,
interface and session handling. Passing its tests is not that proof.

## VOLE hash interface

The VOLE variant uses one nonzero global coefficient, coordinate-separated hashes,
and a random-oracle proof. The theoretical per-session bound is
`q_H * t / (2^128 - 1) + t * 2^-lambda`. Here `q_H` includes queries to the target
session's oracle by the adversary and environment, including queries they make
through other protocols. The proof assumes a session-local oracle namespace;
composition requires separate oracles or unique session identifiers in the domain.

The historical hash interface includes a fixed `APEQ-v1-vole-equality` tag,
coordinate and field value, but **no session identifier**. Fresh-session
measurements do not establish multi-session UC security of this interface.
V4 binds a protocol/version/role tag, both parties' fresh 256-bit nonces, input
width, batch length, coordinate and field value using fixed-width encodings.
Nonce exchange is included in setup. With fresh ideal correlations, sequential
session bounds add, together with at most `s*(s-1)/2^257` for honest-nonce collision
over `s` sessions. This repairs the hash namespace; it is not a concurrent UC
proof for the concrete correlation generator or network stack. Inputs for each
session must be fixed independently of that session's oracle namespace.
For fixed unequal inputs in the random-oracle model the false-accept term is
`2^-lambda`; this is distinct from the overall privacy bound above.

## Malicious parties

The published implementation does not provide full malicious security. A malicious
extension needs appropriate consistency checks (including retrieval/input
consistency), enforced nonzero coefficients and a new proof with new measurements.
An ideal-OLE observation about a malicious querier does not provide these properties
for the implemented retrieval backend. Honest nonzero sampling is not enforcement
against a deviating holder. No such extension is claimed by this release.

No independent production security audit is claimed. V4 changes the point and
session interfaces explicitly; it does not upgrade the threat model to malicious
security or certify a concrete security level for the historical packed backend.
