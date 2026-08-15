import { Link } from "react-router-dom";
import { Signpost, ArrowLeft } from "@phosphor-icons/react";

// Friendly fallback for unknown routes (frontend-ux §76): instead of a blank screen,
// tell the user the page doesn't exist and offer a way back to the project console.
export function NotFoundPage() {
  return (
    <div className="not-found-page">
      <Signpost size={40} />
      <h1>页面不存在</h1>
      <p>你访问的地址不在 Studio 里，可能已被移动或删除。</p>
      <Link to="/" className="btn primary">
        <ArrowLeft size={16} /> 返回项目
      </Link>
    </div>
  );
}
