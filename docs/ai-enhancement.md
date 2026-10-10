# AI Enhancement

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
  conceal the background in black, without inpainting/reconstruction. They do not remove
  hidden pixels from MAX/MIN/AVG: use a measurement region to restrict readings.
- DJI SDK continues to handle radiometric decoding and available official palette LUTs.
  AI interpretation is a separate OpenAI service; local OpenCV renders the display edits.
- AI outlines are approximate. Use manual freehand focus for precise boundaries. No
  recovery of absent detail or diagnostic accuracy is promised.
- Chat text is held in browser memory for the current image, not stored in activity logs.
  The activity log records only that an AI proposal was requested. Applied settings and
  masks persist through the normal workspace/package workflow.

## Verification

Automated tests cover source/matrix preservation, mask rendering and serialization,
owner-only access, missing configuration, invalid proposals, no implicit saving,
provider request format, stripped metadata, and concurrent-request cleanup.
UI verification uses a synthetic local image and a mocked provider. Live provider
quality requires a configured key and representative insulator images.

API references: https://developers.openai.com/api/docs/guides/images-vision and
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses
