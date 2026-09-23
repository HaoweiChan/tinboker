import { Link } from 'react-router-dom';

export function ServiceLinks() {
  return (
    <nav aria-label="服務與消費者資訊" className="flex flex-wrap gap-x-5 gap-y-3 text-xs text-muted-foreground">
      <Link className="hover:text-foreground hover:underline" to="/membership">服務與會員方案</Link>
      <Link className="hover:text-foreground hover:underline" to="/contact">客服聯絡</Link>
      <Link className="hover:text-foreground hover:underline" to="/terms">服務條款</Link>
      <Link className="hover:text-foreground hover:underline" to="/privacy">隱私權政策</Link>
      <Link className="hover:text-foreground hover:underline" to="/refund">退款說明</Link>
    </nav>
  );
}
