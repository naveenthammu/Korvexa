import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CreditCard, Minus, Plus, Receipt, ShoppingCart, WifiOff } from "lucide-react";
import { apiRequest } from "../lib/api";
import { Button } from "../components/ui/button";

type QrVariant = {
  name: string;
  price_delta: string;
};

type QrAddon = {
  name: string;
  price: string;
};

type QrProduct = {
  id: string;
  category_id?: string | null;
  name: string;
  description?: string | null;
  price: string;
  tax_rate: string;
  image_url?: string | null;
  variants?: QrVariant[];
  addons?: QrAddon[];
};

type QrMenu = {
  branch: { id: string; name: string; address?: string; phone?: string };
  table: { id: string; name: string; status: string; floor_area: string };
  categories: Array<{ id: string; name: string }>;
  products: QrProduct[];
};

type QrOrder = {
  id: string;
  total: string;
  payment_status: string;
  kds_status: string;
};

type RazorpayCheckoutResponse = {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
};

type QrRazorpayCheckout = new (options: {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  prefill?: { name?: string; contact?: string };
  theme?: { color: string };
  handler: (response: RazorpayCheckoutResponse) => void;
  modal?: { ondismiss?: () => void };
}) => { open: () => void };

function apiError(error: unknown, fallback: string) {
  if (!(error instanceof Error) || !error.message) return fallback;
  try {
    const payload = JSON.parse(error.message);
    return payload?.errors?.[0]?.detail || payload?.message || payload?.detail || fallback;
  } catch {
    return error.message;
  }
}

async function loadRazorpayCheckout() {
  if (window.Razorpay) return;
  await new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[src="https://checkout.razorpay.com/v1/checkout.js"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Razorpay checkout failed to load")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Razorpay checkout failed to load"));
    document.body.appendChild(script);
  });
}

export default function QrOrderPage() {
  const params = new URLSearchParams(window.location.search);
  const branchId = params.get("branch_id") || "";
  const tableId = params.get("table_id") || "";
  const [menu, setMenu] = useState<QrMenu | null>(null);
  const [cart, setCart] = useState<Record<string, number>>({});
  const [selectedVariants, setSelectedVariants] = useState<Record<string, string>>({});
  const [selectedAddons, setSelectedAddons] = useState<Record<string, string[]>>({});
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [note, setNote] = useState("");
  const [order, setOrder] = useState<QrOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadMenu() {
      setLoading(true);
      setError("");
      try {
        const response = await apiRequest<{ success: boolean; data: QrMenu }>(`/api/v1/qr/menu?branch_id=${branchId}&table_id=${tableId}`);
        if (!cancelled) setMenu(response.data);
      } catch (err) {
        if (!cancelled) setError(apiError(err, "This QR link is not active."));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (branchId && tableId) loadMenu();
    else {
      setError("QR link is missing table details.");
      setLoading(false);
    }
    return () => { cancelled = true; };
  }, [branchId, tableId]);

  const cartItems = useMemo(() => {
    if (!menu) return [];
    return Object.entries(cart)
      .map(([productId, quantity]) => ({ product: menu.products.find((item) => item.id === productId), quantity }))
      .filter((item): item is { product: QrProduct; quantity: number } => Boolean(item.product) && item.quantity > 0);
  }, [cart, menu]);

  const totals = useMemo(() => {
    return cartItems.reduce((sum, item) => {
      const variant = item.product.variants?.find((option) => option.name === selectedVariants[item.product.id]);
      const addons = item.product.addons?.filter((option) => selectedAddons[item.product.id]?.includes(option.name)) || [];
      const price = Number(item.product.price || 0)
        + Number(variant?.price_delta || 0)
        + addons.reduce((addonTotal, addon) => addonTotal + Number(addon.price || 0), 0);
      const tax = price * (Number(item.product.tax_rate || 0) / 100);
      return sum + ((price + tax) * item.quantity);
    }, 0);
  }, [cartItems, selectedAddons, selectedVariants]);

  const cartQuantity = useMemo(
    () => cartItems.reduce((quantity, item) => quantity + item.quantity, 0),
    [cartItems],
  );

  function changeQty(productId: string, delta: number) {
    setCart((prev) => {
      const next = Math.max(0, (prev[productId] || 0) + delta);
      const copy = { ...prev };
      if (next <= 0) delete copy[productId];
      else copy[productId] = next;
      return copy;
    });
  }

  function toggleAddon(productId: string, addonName: string) {
    setSelectedAddons((current) => {
      const selected = current[productId] || [];
      return {
        ...current,
        [productId]: selected.includes(addonName)
          ? selected.filter((name) => name !== addonName)
          : [...selected, addonName],
      };
    });
  }

  async function placeOrder(payAfter = false) {
    if (!menu || cartItems.length === 0) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await apiRequest<{ success: boolean; data: QrOrder }>("/api/v1/qr/orders", {
        method: "POST",
        body: JSON.stringify({
          branch_id: menu.branch.id,
          table_id: menu.table.id,
          customer_name: customerName.trim() || "QR Guest",
          customer_phone: customerPhone.trim() || undefined,
          notes: note.trim() || undefined,
          items: cartItems.map((item) => ({
            product_id: item.product.id,
            quantity: item.quantity,
            variant_name: selectedVariants[item.product.id] || undefined,
            addons: (selectedAddons[item.product.id] || []).map((name) => ({ name })),
            notes: note.trim() || undefined,
          })),
        }),
      });
      setOrder(response.data);
      if (payAfter) {
        await payOnline(response.data);
      }
    } catch (err) {
      setError(apiError(err, "Could not place order."));
    } finally {
      setSubmitting(false);
    }
  }

  async function payOnline(targetOrder = order) {
    if (!targetOrder || !menu) return;
    setPaying(true);
    setError("");
    try {
      await loadRazorpayCheckout();
      const gateway = await apiRequest<{
        success: boolean;
        data: { key_id: string; gateway_order_id: string; amount_paise: number; currency: string };
      }>(`/api/v1/qr/orders/${targetOrder.id}/payments/gateway`, { method: "POST" });
      const RazorpayCheckout = window.Razorpay as unknown as QrRazorpayCheckout | undefined;
      if (!RazorpayCheckout) throw new Error("Razorpay checkout is unavailable");
      await new Promise<void>((resolve, reject) => {
        const checkout = new RazorpayCheckout({
          key: gateway.data.key_id,
          amount: gateway.data.amount_paise,
          currency: gateway.data.currency,
          name: menu.branch.name,
          description: `Table ${menu.table.name} order`,
          order_id: gateway.data.gateway_order_id,
          prefill: { name: customerName, contact: customerPhone },
          theme: { color: "#0d9488" },
          handler: async (response) => {
            try {
              const verified = await apiRequest<{ success: boolean; data: QrOrder }>(`/api/v1/qr/orders/${targetOrder.id}/payments/gateway/verify`, {
                method: "POST",
                body: JSON.stringify({
                  gateway_order_id: response.razorpay_order_id,
                  gateway_payment_id: response.razorpay_payment_id,
                  gateway_signature: response.razorpay_signature,
                }),
              });
              setOrder(verified.data);
              resolve();
            } catch (err) {
              reject(err);
            }
          },
          modal: { ondismiss: () => reject(new Error("Payment cancelled")) },
        });
        checkout.open();
      });
    } catch (err) {
      setError(apiError(err, "Online payment failed."));
    } finally {
      setPaying(false);
    }
  }

  if (loading) {
    return <main className="qr-order-shell"><div className="qr-order-state">Loading menu...</div></main>;
  }

  if (error && !menu) {
    return (
      <main className="qr-order-shell">
        <div className="qr-order-state error"><WifiOff size={28} /><span>{error}</span></div>
      </main>
    );
  }

  if (!menu) return null;

  return (
    <main className="qr-order-shell">
      <header className="qr-order-header">
        <div>
          <span>Table {menu.table.name}</span>
          <h1>{menu.branch.name}</h1>
          <p>{menu.branch.address || "Order from your table"}</p>
        </div>
        <Receipt size={28} />
      </header>

      {order ? (
        <section className="qr-order-confirm">
          <CheckCircle2 size={42} />
          <h2>Order sent to kitchen</h2>
          <p>Order #{order.id.slice(0, 8)} is now in the kitchen queue.</p>
          <strong>Rs. {Number(order.total).toFixed(2)}</strong>
          {order.payment_status === "paid" ? (
            <span className="qr-paid">Payment completed</span>
          ) : (
            <Button type="button" onClick={() => payOnline()} disabled={paying}>
              <CreditCard size={16} /> {paying ? "Opening payment..." : "Pay online"}
            </Button>
          )}
          {error && <small className="qr-error">{error}</small>}
        </section>
      ) : (
        <>
          <section className="qr-customer-card">
            <input value={customerName} onChange={(event) => setCustomerName(event.target.value)} placeholder="Your name" />
            <input value={customerPhone} onChange={(event) => setCustomerPhone(event.target.value)} placeholder="Phone number" />
          </section>

          <section className="qr-menu-list">
            {menu.products.map((product) => {
              const qty = cart[product.id] || 0;
              return (
                <article key={product.id} className="qr-menu-item">
                  <div className="qr-menu-details">
                    <h2>{product.name}</h2>
                    {product.description && <p>{product.description}</p>}
                    <strong>Rs. {Number(product.price).toFixed(2)}</strong>
                    {Boolean(product.variants?.length) && (
                      <label className="qr-variant-field">
                        <span>Size</span>
                        <select
                          aria-label={`Size for ${product.name}`}
                          value={selectedVariants[product.id] || ""}
                          onChange={(event) => setSelectedVariants((current) => ({ ...current, [product.id]: event.target.value }))}
                        >
                          <option value="">Standard</option>
                          {product.variants!.map((variant) => (
                            <option key={variant.name} value={variant.name}>
                              {variant.name} (+Rs. {Number(variant.price_delta).toFixed(2)})
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                    {Boolean(product.addons?.length) && (
                      <div className="qr-addon-list" aria-label={`Add-ons for ${product.name}`}>
                        {product.addons!.map((addon) => (
                          <label key={addon.name} className="qr-addon-option">
                            <input
                              type="checkbox"
                              aria-label={`Add ${addon.name} to ${product.name}`}
                              checked={selectedAddons[product.id]?.includes(addon.name) || false}
                              onChange={() => toggleAddon(product.id, addon.name)}
                            />
                            <span>{addon.name} (+Rs. {Number(addon.price).toFixed(2)})</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="qr-qty">
                    <button type="button" aria-label={`Remove ${product.name}`} onClick={() => changeQty(product.id, -1)} disabled={qty === 0}><Minus size={14} /></button>
                    <span>{qty}</span>
                    <button type="button" aria-label={`Add ${product.name}`} onClick={() => changeQty(product.id, 1)}><Plus size={14} /></button>
                  </div>
                </article>
              );
            })}
          </section>

          <section className="qr-cart-bar">
            <div>
              <span>{cartQuantity} {cartQuantity === 1 ? "item" : "items"}</span>
              <strong>Rs. {totals.toFixed(2)}</strong>
            </div>
            <div className="qr-cart-actions">
              <Button type="button" onClick={() => placeOrder(false)} disabled={cartItems.length === 0 || submitting || paying}>
              <ShoppingCart size={16} /> {submitting ? "Sending..." : "Place order"}
              </Button>
              <Button type="button" onClick={() => placeOrder(true)} disabled={cartItems.length === 0 || submitting || paying}>
                <CreditCard size={16} /> {paying ? "Opening payment..." : "Order & pay"}
              </Button>
            </div>
          </section>
          {error && <div className="qr-floating-error">{error}</div>}
        </>
      )}
    </main>
  );
}
