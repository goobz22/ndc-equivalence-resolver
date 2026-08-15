"use client";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="error-box">
      <b>Something went wrong loading this page.</b>
      <p style={{ margin: "0.5rem 0" }}>
        {error.message || "The data API did not respond."}
        {" — if you are running locally, check that the API server "}
        (uvicorn on :8600) is up.
      </p>
      <button onClick={() => reset()}>Try again</button>
    </div>
  );
}
