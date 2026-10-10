# Insulator Focus

The toolbar opens a chat and preview window. Describe an insulator to retain, background
to hide, or gentle contrast/detail changes. Review the proposed outlines, compare with
the current workspace, then Apply. Requests can refine the pending proposal before applying.
Undo enhancement reverses the applied settings. Save draft, editable packages, report PNG,
and Save to inspection use the same renderer/settings.

## Server setup

Set `OPENAI_API_KEY` in the protected server `.env` (never in frontend code or chat).
`OPENAI_ENHANCEMENT_MODEL` defaults to `gpt-4.1`; it must support vision and strict
structured outputs on the Responses API. Recreate the API service after configuring it.
Existing web search uses the same API key, but its model setting is separate.
With no key, the dialog explains setup and offers the manual focus tool. There is no
simulated AI fallback in production. Provider authentication, model availability, and
billing/quota errors are reported without exposing the key or upstream response body.

## What happens

- Authenticated users can request proposals only for images in their own workspace.
- A re-encoded visual preview (at most 1280 pixels on its longest side), current display
  settings, prompt, and up to 12 conversation turns are sent to OpenAI. EXIF/GPS metadata,
  original radiometric files, and temperature matrices are not sent. Image pixels can
  still contain visible sensitive information; the dialog discloses the transfer.
- Responses use `store:false`; this does not promise zero retention by the provider.
- The model proposes validated polygons and display parameters, never generated imagery
  or executable operations. Self-crossing/out-of-range polygons are rejected.
- Only one request per user and three per API process may run concurrently. Requests
  have a 70-second provider timeout and bounded input/output. Closing cancels the browser
  request, but an upstream request already sent may still finish and consume API usage.
- Original pixels, calibrated matrices, and analysis parameters are unchanged. Masks
  recolor the background in muted blue (scene texture retained) or conceal it in black,
  without inpainting/reconstruction. Blue does not mean zero temperature or correct
  reflected radiation. Exports retain source dimensions and include processing disclosure in PNG metadata.
  Focus readings exclude background pixels. Original full-frame readings remain available;
  for additional independent regions, use a measurement region to restrict readings.
- DJI SDK continues to handle radiometric decoding and available official palette LUTs.
  AI interpretation is a separate OpenAI service; local OpenCV renders the display edits.
- AI outlines are approximate. Use the manual polygon and brushes for precise boundaries. No
  recovery of absent detail or diagnostic accuracy is promised.
- Chat text is held in browser memory for the current image, not stored in activity logs.
  The activity log records only that an AI proposal was requested. Applied settings and
  masks persist through the normal workspace/package workflow.

## Verification

Automated tests cover source/matrix preservation, mask rendering and serialization,
owner-only access, missing configuration, invalid proposals, no implicit saving,
provider request format, stripped metadata, and concurrent-request cleanup.
UI verification covers the supplied DJI M4T image, saved polygon and brush masks,
zoom, pan, undo/redo, preview/apply, and reopening. AI tests use a mocked provider;
live provider quality requires a configured key.

API references: https://developers.openai.com/api/docs/guides/images-vision and
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses

## Suppress background heat colors without AI

The dialog always offers an independent manual workflow. Click **1. Outline the
insulator to keep**, then click ordered points around the target in the full image
(minimum three, maximum 256). **Undo selection** corrects the last click or brush stroke; **Redo selection** restores it. Click **2. Preview
blue background** and inspect the mask, then **3. Apply changes** in the fixed footer.
**Done** returns to the workspace; **Save draft** or **Save to inspection** persists it.
The preview itself does not change the workspace. Invalid outlines are rejected by
existing server validation. The existing focus area can be reused. AI suggestions and
chat input are hidden when no API key is configured, to avoid suggesting unavailable
edits. This manual workflow sends no image to OpenAI.

Background appearance in Enhance image offers muted blue, solid navy or darkening, with a suppression
strength slider. Manual blue previews leave insulator detail settings at zero to preserve
its existing colors. Stored settings without background_mode keep the prior darkening
behavior. AI proposals can recolor only specified mountain/cloud polygons as well as
recoloring everything outside a target outline.

## Precise mask editing and calibrated JPEGs

The **Insulator Focus** toolbar button opens the selection/preview dialog. Polygon, Add
brush, Erase brush, adjustable brush size, 1–6× zoom, Pan, Fit, undo/redo, clear, reset and
mask visibility let users retain fittings and remove heat between the discs. Coordinates
and brush radii are fractions of the source frame, independent of viewport size/zoom.
Brushed masks are refined in this editor rather than transformed with the old box handles.

The preset preserves original selected pixels by default, suppresses the background in
navy blue, and uses narrow outward feathering. **Enhance image → Insulator focus** provides
original-pixel preservation, subtle bounded local brightness/contrast/gamma/denoise/
sharpening, background strength, solid navy or contextual blue, and edge feathering.
**Insulator Auto Range** explicitly switches to a calibrated palette and derives both
endpoints from valid temperatures in the exact mask. It releases original-color preservation.
Global full-frame data, saved independent measurement regions and source files are unchanged.

Original DJI radiometric JPEGs are decoded by the existing SDK regardless of filename.
The user's two M4T samples (1280×1024 JPEG, 640×512 matrix) decode with SDK 1.8. Exported
JPEGs can lose that payload: their visual editing remains available, but readings, palettes
and auto range require a valid matrix. No values are inferred from RGB. The provided
version-1 .thermalpkg without a matrix reopens in visual-only mode.

**Enhanced PNG · full resolution** exports the full source dimensions without annotations
or crop. **Report image** includes the existing annotations and optional crop, at source
resolution. Both add processing metadata without padding the image. **Untouched original**
downloads original bytes. Editable packages retain the original, brush strokes, precise
mask geometry, enhancement settings and matrix when present. Existing packages remain
readable. Version 1 is unchanged because new optional settings have legacy defaults.

Assisted chat selection still requires an administrator's OpenAI API key; manual
selection does not transmit images to an AI provider.
