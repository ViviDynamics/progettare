# Progettare image generation record

Approved canonical assets: [mascot PNG](progettare-architect.png),
[mark SVG](progettare-mark.svg), and [mark PNG](progettare-mark.png).
The final mascot and mark are both v3. See the [brand guide](README.md),
v2 correction record, and v3 projection and hand style corrections below.

First concept generated 2026-10-12 using the built-in image generation tool.
The original PNG files are unmodified outputs from the built-in image generation tool.
The mascot has a transparent background. The icon has an opaque forest-green
square and white outside its rounded corners, matching the sibling emblem
concepts. Its initial transparent generation introduced gaps in the square;
a targeted edit restored the background before saving the final rendering.

- `progettare-architect-v1.png`: the family gentleman as a technical architect,
  laying out an ivory plan with a brass drafting compass. References:
  Scrutare's `scrutare-editor.png` and QAre's `qare-tester.png` from their
  sibling repositories' `docs/brand/` directories.
- `progettare-mark-v1.png`: an ivory hand operating a brass drafting compass over
  simple plan marks, on the family's forest-green rounded square. Reference:
  the newly generated Progettare architect, followed by the initial icon
  rendering for the background correction. This is a raster icon concept;
  the sibling projects' production marks are native SVGs.

Family palette: forest `#214E3D`, ivory `#F6F3EB`, brass `#BC9654`, and ink
`#243C32`, with warm skin and silver-white hair in the mascot.

## Architect mascot prompt

Use case: identity-preserve. Asset type: Progettare software brand mascot, transparent cutout.
Input image 1 is Scrutare's copy editor and input image 2 is QAre's tester. Both are REFERENCE images for the existing family character's face, likeness, proportions, illustration style, contours and colors.
Create their Progettare sibling: the SAME warm older gentleman, swept silver-white hair, round dark forest-green spectacles, clean-shaven face, warm peach skin, expressive eyes and familiar rounded nose. Progettare is a technical architect and planner who surveys a codebase and creates a single blueprint for others to implement. He should look like a thoughtful, capable old-fashioned architect patiently working out a sound plan.
Dress him in an ivory open-collar shirt with sleeves rolled to the elbows, a tailored forest-green waistcoat with restrained brass buttons. No tie, no apron, no visor, no hard hat. Expression: eyes focused down through his spectacles on the plan, brows gently gathered in concentration, a small assured closed-mouth smile; calm, observant and purposeful.
He holds a compact rectangular drafting board tilted upward across his lower chest, supported at its lower right edge by his left hand. An ivory plan sheet rests on the board, with a few clean forest-green architectural plan lines: a simple arrangement of connected rectangular rooms and one short construction arc. His right hand holds a classic brass drafting compass by its top hinge, two clearly separated slender legs, with one point resting on the plan as he lays out the arc. The compass is recognizable, not scissors, and its hinge and both legs are visible. The hands must be anatomically coherent; each has five fingers, natural grip. Keep props simple and readable.
Waist-up compact centered bust, entire head and both arms, board, hands, and compass fully inside frame with comfortable clear margin. Match references' polished classic editorial illustration: bold clean dark-green contours, broad flat shapes, restrained soft shading, dignified friendly charm. Forest #214E3D, ivory #F6F3EB, brass #BC9654, ink #243C32 plus the references' skin and hair shades. No blue.
Genuinely transparent background, no rectangle, no floor, no shadow outside character. No text, letters, numerals, words, watermark, surrounding decorations, buildings in background, computer, phone, money, baton, ruler bundle, extra tools or extra people. Preserve the established family likeness faithfully. Generate one final mascot image.

## Icon rendering prompt

Use case: logo-brand. Asset type: Progettare small brand emblem and app icon rendering.
Input image 1 is the newly created Progettare architect mascot, a REFERENCE ONLY for the compass action and ivory sleeve. Do not redraw his head, body, drafting board or face.
Create ONE refined emblem in the existing family style of QAre and Scrutare: an anatomically convincing ivory hand with an ivory shirt cuff operating a brass drafting compass to lay out a plan. Flat vector-like artwork in exactly three colors: forest green #214E3D, warm ivory #F6F3EB and brass #BC9654.
Design: the hand enters diagonally from the upper right, broad ivory cuff near the upper right margin, then the wrist and a natural pinching grip on the compass's circular top hinge in the center. Thumb and index finger visibly pinch the hinge, three remaining fingers curl naturally into one clear silhouette. Keep the thumb separate and the fingers proportional. The compass has exactly two clear tapered brass legs spreading downward in an inverted V, one point toward the lower left, the other toward the lower middle/right. Recognizable drafting compass, no scissor handles. Beneath the compass points are two bold simple ivory right-angle floor-plan line fragments, and one short brass construction arc touched by the drawing point; use large simple geometry with open forest negative space, no detailed blueprint, no paper sheet outline. Think a classic publisher's emblem or a carefully drawn heraldic hand, not a glove emoji, cursor, fist or clip art.
Composition: centered inside a solid forest-green rounded square, square fills the canvas with understated rounded corners (corner radius about 22% of square width); actually transparent outside the rounded corners. Hand, cuff, compass and plan marks occupy approximately 78% of the square, comfortable uniform margin. Clear silhouette, professional optical balance, bold enough to read at 32px. A coherent hand with at most three green interior finger separation strokes. No outlines in a fourth color.
No gradients, shading, textures, shadows, border, words, letters, numbers, watermark, checkmarks, sparkles, face, buildings, ruler, pencil, second hand or additional tools. Flat three-color brand mark. Generate one final icon image.

## Icon background refinement prompt

Use case: precise-object-edit. Asset type: Progettare brand emblem rendering.
Edit the attached icon to correct ONLY its background and flat color treatment. Preserve the exact existing hand anatomy, cuff, grip, brass compass, floor-plan lines, arc, relative positions, scale and composition.
Replace the entire background with ONE perfectly uniform solid opaque forest-green #214E3D rounded square, filling the full canvas, with a corner radius of approximately 22% of the width. Every location inside this rounded square MUST be solid forest green unless occupied by the ivory or brass foreground. Restore all dark or transparent holes and mottled patches inside the square to the exact same solid forest-green fill. No cutouts through the square. Outside the four rounded corners use plain solid white. The final image is fully opaque.
Flatten all foreground ivory areas to uniform #F6F3EB and all brass areas to uniform #BC9654; all green finger and cuff separation areas are exactly #214E3D. Retain the existing shapes and graceful hand. This is a flat three-color family emblem, matching QAre and Scrutare, not a shaded illustration. No gradients, texture, glows, shadows, new objects, outlines, text, watermark or changed geometry.

## Corrected assets (v2)

- `progettare-architect-v2.png`: revised transparent mascot. The compass grip
  has a distinct thumb and short handle, and the supporting hand wraps around
  the board with its thumb on the front. The plan has cleaner connected walls.
  The stray arc was removed, so the compass reads as measuring the plan.
- `progettare-mark-v2.svg`: production vector mark. The hand and cuff were
  traced from the built-in image tool's revised mark concept using VTracer,
  then normalized to the exact ivory color. The compass, arc, and background
  are native SVG geometry. The two compass tips are `(380, 955)` and
  `(776, 955)`; the arc has radius `396`, starts at the drawing tip, and is
  centered on the needle. The arc is ivory to distinguish the drawn line from
  the brass tool. Both legs connect to the hinge, and the handle
  reaches beneath the fingers. The disconnected plan fragments and decorative
  leg knob were removed. Only the family's three exact colors are used.
- `progettare-mark-v2.png`: a 1254 × 1254 CairoSVG export of the SVG, with
  transparent corners. This is a vector export, not an image-generator output.

The originals remain available for comparison. The revised mascot was checked
on ivory and forest backgrounds, and the SVG was reviewed at 128, 64, and 32 CSS
pixels. No image-generation CLI fallback was used.

### Mascot correction prompt

Use case: precise-object-edit / identity-preserve.
Edit target: the attached Progettare architect mascot. Make a careful professional cleanup, retaining the SAME character, exact facial likeness, silver hair, round forest-green glasses, expression, colors, illustration style, waistcoat and overall pose. This is a correction pass, not a new character.
Correct the hands and working geometry:
1. His right hand at viewer left must naturally pinch the SHORT HANDLE ABOVE the compass hinge between the thumb pad and index finger pad, with the other three fingers comfortably curled into the palm. Show a convincing connected thumb, palm, wrist and knuckles, no extra digits or fused fingertip shapes. A short blunt brass handle, a circular hinge immediately beneath it, and exactly two equal-length tapered compass legs. No decorative spikes or random knobs. One leg has a steel needle tip, the other a graphite drawing tip. Both tips actually touch the same tilted sheet.
2. His left hand at viewer right must visibly support the board: thumb rests on the front face just inside the right edge, and the other fingers wrap around the board edge and underneath it. Clearly distinguish the thumb from curled fingers. The board's thin edge occludes fingers correctly. No row of four disconnected noodle fingers pasted onto the front of the paper.
3. Clean the drawing to a sparse, coherent architectural floor plan: an outer rectangle with two simple connected interior walls and deliberate doorway gaps. All straight lines share the same board perspective and clean consistent line weights. Remove stray duplicate segments, accidental breaks, doubled scratchy outlines and illegible squiggles.
4. Show ONE delicate construction arc physically centered on the compass's fixed needle, meeting the graphite tip EXACTLY. Account for the tilted plane of the paper: a circular arc in that plane appears elliptical from our view. The arc curves around the needle, not away from it, and must not float away from the drawing tip.
Keep his head and gaze directed down to the drafting action with a calm slight smile, the same family likeness, broad dark-green contours and restrained shading. Palette forest #214E3D, ivory #F6F3EB, brass #BC9654, ink #243C32 plus existing warm skin and silver hair. Preserve the board as a thin professional drafting board.
Centered waist-up silhouette with a little more breathing room: minimum 6% clear margin on every side, all hair, elbows and board corners fully inside. True transparent background. The entire interior of the character must be opaque, including all skin, shirt, hair and green waistcoat; transparency belongs only outside the silhouette and in real open gaps. Crisp clean antialiased edges without green/gold fringes or stray pixels. No text, new props, background scenery, drop shadow or watermark.

### Mascot final cleanup prompt

Use case: precise-object-edit. Edit target: attached corrected Progettare architect.
Make ONE tiny cleanup: ERASE the thin curved dark-green arc on the ivory plan sheet between and to the right of the two compass tips. Replace that curved stroke with clean ivory paper matching the nearby paper. There must be NO curved arc anywhere on the sheet after this edit. Keep the straight architectural floor-plan walls exactly as they are. The compass is simply measuring a distance on the plan.
Preserve EVERYTHING ELSE exactly: the gentleman's face, eyes, hair, glasses, expression, clothes, both improved hand grips, fingernails, board, compass hinge and legs, straight plan lines, pose, colors, framing and proportions. Do not add or alter any objects.
Retain a truly transparent background and make all character, board and clothing interiors fully opaque with crisp antialiased edges. No halo, flecks or background.

### Mark concept correction prompt

Use case: precise-object-edit. Edit target: attached Progettare mark.
Refine this existing hand-and-drafting-compass emblem into a polished, readable brand mark. Retain the identity: ivory hand and shirt cuff from upper right, brass compass pointing down, forest-green rounded square. Preserve the classic heraldic/editorial hand style.
Correct the anatomical grip: thumb and index finger naturally pinch a SHORT BLUNT vertical compass handle ABOVE its circular hinge; the other three fingers are comfortably curled together toward the palm with clear but restrained separations. Wrist connects naturally to cuff. No claw-like stretched index finger, extra digits, floating thumb, triangular spike or blade above the hinge.
Correct the compass: a short handle over one circular hinge and exactly TWO equal-length tapered brass legs spreading downward, one needle point and one drawing point on the same horizontal baseline. Remove the arbitrary round knob halfway down the left leg. Keep both legs continuous, generous green separation between them, and avoid tangencies with the hand.
Correct the arc geometry: the needle tip is the center of a circle; the drawing tip sits on that circle. Draw one clean brass circular arc at exactly that radius, with one endpoint touching the drawing tip. From that endpoint the arc sweeps downward and TOWARD the needle's vertical axis, never outward away from the needle. Suggested layout, normalized to square: needle tip (0.32, 0.73), drawing tip (0.63, 0.73), hinge (0.475,0.44); circle center is the needle, radius 0.31; the arc runs about 28 degrees from the drawing tip downward-left. No detached arc, no ellipse, no wrong center.
Remove BOTH disconnected ivory floor-plan zigzags and the small accidental ivory notch beside the needle. The clear hand, compass and single correct arc communicate planning without extra fragments.
Use large filled shapes and at most three internal green finger-separation strokes. True flat solid colors: forest #214E3D, ivory #F6F3EB, brass #BC9654, without gradients, shading, mottled texture or shadows. Smooth clean edges. Background is one fully OPAQUE uniform forest-green rounded square filling the canvas with corner radius about 22%; WHITE outside the four rounded corners. Do not create transparent holes or faded patches within the green square. Foreground occupies about 78% of square with balanced margins; cuff and arc both fully inside. No text, borders, additional symbols, watermark, extra tools or second hand.

The generated mark still placed the arc incorrectly. Its hand and cuff were
retained by tracing; the final compass and arc were constructed in SVG as
described above.

## Mark projection correction (v3)

The v2 arc had the correct radius in screen space but did not represent a
circle lying on the drawing surface. In `progettare-mark-v3.svg`, the circle
is projected orthographically onto a plane with depth foreshortened to one
third, equivalent to a view about 19.47 degrees above the surface. Its projected
ellipse has radii `(396, 132)` and center `(380, 955)`, at the fixed needle.
The arc meets the drawing tip at `(776, 955)` and sweeps 100 degrees toward
the viewer, ending at `(311.235, 1084.995)`. The longer, flatter arc makes the
drawing plane visible without adding a surface outline.

This revision changes only the arc geometry and its description. The mascot,
hand, compass, palette, and background retain their v2 artwork. The PNG is a
1254 × 1254 transparent export from CairoSVG. The SVG geometry and raster
export were checked; no image generation was needed for this vector edit.

## Mascot hand style correction (v3)

The final mascot removes the two outlined thumbnails to match the smooth
fingertips used by Scrutare and QAre. `progettare-architect-v3.png` is the
unmodified output of a targeted built-in image edit of v2 and is also saved
as the canonical `progettare-architect.png`. The projected-arc mark remains v3.

### Prompt

Use case: precise-object-edit.
Edit target: the attached approved Progettare architect mascot.
Make one small style correction: remove the two outlined thumbnail ovals, one on the hand holding the compass near the middle of the image and one on the hand supporting the board at the right. Fill those tiny interior oval details with the adjacent warm skin color and its existing gentle shading. The fingers should have smooth, plain surfaces without drawn nails or cuticle lines, matching the simple hand treatment of the other family mascots.
Keep the silhouette, finger shapes, grips, dark outer contours, face, hair, glasses, expression, clothing, compass, board, plan, colors, framing and all other details exactly as in this image. Do not redesign or reposition anything.
Preserve the transparent background and the opaque illustrated character. Output one corrected mascot PNG.
