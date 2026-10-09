PREVIEW WORKFLOW OVERRIDE: normal-quality design, deferred structural verification.
This section overrides the validation, connection-repair and final-delivery phases
of the instructions above for this turn, including follow-up edits. Keep their
design, reference-discovery, parts-selection and construction guidance.

1. Design the full requested model at the requested scale and complexity. Write
   the normal design brief, study relevant category guidance and references, and
   choose suitable parts. Finish its major modules and defining details. Do not
   reduce scope, piece count or visual detail to rush a first draft. Do not add
   pointless bricks to inflate piece count. For edits, reuse the existing
   generator and preserve the design's scale and unaffected details.
2. Construct with the usual builder/serializer and ordinary brick alignment,
   stacking and module anchors. Keep syntax, references and execution valid.
   For JSON plans, use the familiar build command through run_toolkit. In
   preview mode it keeps construction/syntax checks and writes the MPD while
   deferring global geometry/contact checks. Its successful exit means the
   preview was constructed, not structurally verified. Use run_toolkit rather
   than invoking build through run_shell, which bypasses this adapter. Existing
   Python generators may also use the ordinary builder/serializer. Do not
   inspect or repair connectivity merely to make a preview pass.
3. Render the assembled model with the ordinary render command (which does not
   check connectivity) and open the actual image
   with view_image BEFORE publication. Compare its silhouette, proportions,
   depth and feature detail with the brief. Make at most one focused visual
   refinement, then render/open the revised model if changed. Avoid render
   sweeps and repeated aesthetic polishing. If rendering fails, report that
   visual review was unavailable and publish the otherwise complete design.
4. Defer exhaustive geometry/contact validation, disconnected-part repairs,
   per-instruction-step validation, check-model, CAD/BOM comparison and checked
   building-instruction export to Verify Build. Do not invoke these checks as
   part of generators or render scripts. Keep choosing allowed catalog parts,
   but defer the complete availability/quantity audit. An unchecked preview may
   contain unsupported connections or overlaps; it is not certified buildable.
5. Once the full design and bounded visual review are done, call publish_model
   once on the self-contained output MPD, then stop. Publication preserves the
   reviewed design without running another render or structural check. Leave
   the design brief, generator and short continuation notes in output/NOTES.md
   so Verify Build can repair the structure without simplifying the design.
