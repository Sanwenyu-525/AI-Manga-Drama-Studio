import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import "@fontsource-variable/geist";
import "./styles.css";
import "./styles/features/timeline.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

// The window frame (custom TitleBar + routed content) lives in the router's
// layout route so the TitleBar can navigate; in a plain browser the TitleBar
// renders nothing and the frame keeps the same structure.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </QueryClientProvider>
  </React.StrictMode>,
);
