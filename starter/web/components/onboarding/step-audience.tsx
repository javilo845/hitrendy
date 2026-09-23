"use client";

interface Props {
  data: {
    country: string;
    city: string;
    target_audience: string;
    primary_product: string;
  };
  onChange: (field: string, value: string) => void;
}

export function StepAudience({ data, onChange }: Props) {
  return (
    <section>
      <h2 style={{ fontFamily: "var(--font-heading)", marginTop: 0 }}>
        Audiencia y ubicación
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <label htmlFor="aud-country">País *</label>
          <input
            id="aud-country"
            type="text"
            value={data.country}
            onChange={(e) => onChange("country", e.target.value)}
            required
            maxLength={80}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </div>
        <div>
          <label htmlFor="aud-city">Ciudad *</label>
          <input
            id="aud-city"
            type="text"
            value={data.city}
            onChange={(e) => onChange("city", e.target.value)}
            required
            maxLength={100}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </div>
        <div>
          <label htmlFor="aud-product">Producto o servicio principal *</label>
          <input
            id="aud-product"
            type="text"
            value={data.primary_product}
            onChange={(e) => onChange("primary_product", e.target.value)}
            required
            maxLength={240}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </div>
        <div>
          <label htmlFor="aud-target">Audiencia objetivo *</label>
          <textarea
            id="aud-target"
            value={data.target_audience}
            onChange={(e) => onChange("target_audience", e.target.value)}
            required
            maxLength={500}
            rows={3}
            placeholder="Ej: Jóvenes profesionales de 25 a 40 años en Ciudad de México"
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </div>
      </div>
    </section>
  );
}
