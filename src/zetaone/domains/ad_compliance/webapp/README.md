# Web App

A thin frontend client that consumes the compliance API.

## Purpose

This web app is a **consumer** of the API, not a source of business logic. All compliance logic lives in the backend pipeline.

## Features

- **Image Upload**: Upload images via drag-and-drop or file picker
- **API Integration**: Calls the v1 endpoint `/v1/ads/meta/image/check` with image and domain
- **Evidence Visualization**: Displays verdict, risk score, violations, and grouped evidence
- **BBox Overlays (viewer-only)**: Draws OCR and vision bounding boxes on the image using API evidence fields

## Architecture

```
User → Web App → API → Pipeline → Models → Outcome
```

The web app:
1. Accepts image uploads
2. Sends multipart/form-data to `/v1/ads/meta/image/check`
3. Receives JSON outcome
4. Renders violations and evidence visually

## No Business Logic

- No rule checking in the frontend
- No model inference in the frontend
- No compliance calculations
- Just presentation and API calls

## Usage

1. Start the API: `python app.py`
2. Open `index.html` in a browser
3. Upload an image and select domain
4. Click "Analyze Ad" and inspect the returned results

## Future Enhancements

- Image preview with violation overlays
- Evidence highlighting on image
- Batch upload support
- Export results as PDF/JSON
