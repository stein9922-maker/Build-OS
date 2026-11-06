"""Stage 3 procurement workspace: requirements, stock, suppliers, purchase orders and alerts."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from buildos.errors import BuildOSError
from buildos.procurement import (
    net_purchase_quantity,
    outstanding_order_quantity,
    recommended_order_date,
)
from buildos.models import Project
from .common import Services, show_error


STATUSES = ["Draft", "Ordered", "Partially delivered", "Delivered", "Cancelled"]


def _rows(db, sql: str, params=()):
    with db.connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _materials(services: Services, project_id: int):
    return _rows(services.db, "SELECT * FROM materials WHERE project_id=? ORDER BY name", (project_id,))


def _suppliers(services: Services, project_id: int):
    return _rows(services.db, "SELECT * FROM suppliers WHERE project_id=? ORDER BY name", (project_id,))


def render_procurement_tab(services: Services, project: Project) -> None:
    st.subheader("Material procurement")
    st.caption(
        "Track requirements, stock, suppliers and purchase orders. Need dates are calculated from "
        "the current CPM schedule; dates update when the schedule changes."
    )
    try:
        schedule = services.schedule.calculate_schedule(project.id)
    except BuildOSError as exc:
        show_error(exc)
        return
    activity_by_id = {a.activity_id: a for a in schedule.activities}
    mats = _materials(services, project.id)
    suppliers = _suppliers(services, project.id)

    dash, req, stock, supp, orders, prices, reports = st.tabs(
        ["Overview & alerts", "Material requirements", "Inventory", "Suppliers",
         "Purchase orders", "Price comparison", "Reports"]
    )
    with req:
        _render_requirements(services, project.id, activity_by_id, mats)
    # Refresh reads after a requirement or material is added on a Streamlit rerun.
    mats = _materials(services, project.id)
    suppliers = _suppliers(services, project.id)
    with stock:
        _render_inventory(services, project.id, mats)
    with supp:
        _render_suppliers(services, project.id, mats, suppliers)
    suppliers = _suppliers(services, project.id)
    with orders:
        _render_orders(services, project.id, mats, suppliers)
    with prices:
        _render_price_comparison(services, project.id, mats, suppliers)
    with reports:
        _render_reports(services, project.id)
    with dash:
        _render_dashboard(services, project.id, activity_by_id, mats, suppliers)


def _render_requirements(services, project_id, activity_by_id, materials):
    st.markdown("#### Add a material")
    with st.form("proc_add_material", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Material name", placeholder="e.g. Cement")
        category = c2.selectbox("Category", ["Concrete", "Steel", "Masonry", "Finishes", "Electrical", "Plumbing", "General"])
        unit = c3.selectbox("Unit", ["bag", "kg", "tonne", "m³", "m²", "m", "piece", "litre", "set", "box"])
        add = st.form_submit_button("Add material")
    if add:
        if not name.strip():
            st.error("Enter a material name.")
        else:
            try:
                with services.db.connect() as conn:
                    conn.execute(
                        "INSERT INTO materials(project_id,name,category,unit) VALUES(?,?,?,?)",
                        (project_id, name.strip(), category, unit),
                    )
            except Exception as exc:
                st.error(f"Could not add material. It may already exist in this project. Details: {exc}")
            else:
                st.success("Material added.")
                st.rerun()

    materials = _materials(services, project_id)
    if not materials:
        st.info("Add a material above before recording requirements.")
        return
    if not activity_by_id:
        st.info("Add construction activities and calculate a schedule before linking requirements.")
        return

    st.markdown("#### Link material to a scheduled activity")
    activity_options = list(activity_by_id)
    activity_labels = {i: f"{activity_by_id[i].code} — {activity_by_id[i].name}" for i in activity_options}
    material_labels = {m["id"]: f'{m["name"]} ({m["unit"]})' for m in materials}
    with st.form("proc_add_requirement", clear_on_submit=True):
        activity_id = st.selectbox("Construction activity", activity_options, format_func=lambda x: activity_labels[x])
        material_id = st.selectbox("Material", list(material_labels), format_func=lambda x: material_labels[x])
        qty = st.number_input("Required quantity", min_value=0.001, value=1.0, step=1.0)
        notes = st.text_input("Notes (optional)")
        save = st.form_submit_button("Save requirement")
    if save:
        try:
            with services.db.connect() as conn:
                conn.execute(
                    """INSERT INTO activity_materials(project_id,activity_id,material_id,required_quantity,notes)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(activity_id,material_id) DO UPDATE SET
                       required_quantity=excluded.required_quantity, notes=excluded.notes""",
                    (project_id, activity_id, material_id, float(qty), notes.strip()),
                )
        except Exception as exc:
            st.error(f"Requirement was not saved: {exc}")
        else:
            st.success("Requirement saved.")
            st.rerun()

    rows = _rows(services.db, """SELECT am.id, a.code AS activity, a.name AS activity_name,
        m.name AS material, am.required_quantity AS quantity, m.unit, am.notes
        FROM activity_materials am JOIN activities a ON a.id=am.activity_id
        JOIN materials m ON m.id=am.material_id WHERE am.project_id=?
        ORDER BY a.id,m.name""", (project_id,))
    st.markdown("#### Current requirements")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        options = {r["id"]: f'{r["activity"]} — {r["material"]} ({r["quantity"]:g} {r["unit"]})' for r in rows}
        selected = st.selectbox("Requirement to remove", list(options), format_func=lambda x: options[x], key="remove_req")
        if st.button("Remove selected requirement"):
            with services.db.connect() as conn:
                conn.execute("DELETE FROM activity_materials WHERE id=?", (selected,))
            st.success("Requirement removed.")
            st.rerun()
    else:
        st.info("No material requirements recorded yet.")


def _render_inventory(services, project_id, materials):
    st.markdown("#### Update stock")
    if not materials:
        st.info("Add materials in the Material requirements tab first.")
        return
    labels = {m["id"]: f'{m["name"]} ({m["unit"]})' for m in materials}
    with st.form("proc_inventory_form"):
        material_id = st.selectbox("Material", list(labels), format_func=lambda x: labels[x])
        available = st.number_input("Physical stock on site", min_value=0.0, value=0.0, step=1.0)
        reserved = st.number_input("Already reserved for other work", min_value=0.0, value=0.0, step=1.0)
        save = st.form_submit_button("Save inventory")
    if save:
        if reserved > available:
            st.error("Reserved quantity cannot exceed physical stock.")
        else:
            with services.db.connect() as conn:
                conn.execute("""INSERT INTO inventory(material_id,available_quantity,reserved_quantity)
                    VALUES(?,?,?) ON CONFLICT(material_id) DO UPDATE SET
                    available_quantity=excluded.available_quantity,
                    reserved_quantity=excluded.reserved_quantity, updated_at=datetime('now')""",
                    (material_id, float(available), float(reserved)))
            st.success("Inventory saved.")
            st.rerun()
    rows = _rows(services.db, """SELECT m.name AS material,m.unit,
        COALESCE(i.available_quantity,0) AS physical_stock,
        COALESCE(i.reserved_quantity,0) AS reserved,
        MAX(0,COALESCE(i.available_quantity,0)-COALESCE(i.reserved_quantity,0)) AS usable_stock,
        COALESCE(i.updated_at,'Not updated') AS last_updated
        FROM materials m LEFT JOIN inventory i ON i.material_id=m.id
        WHERE m.project_id=? ORDER BY m.name""", (project_id,))
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_suppliers(services, project_id, materials, suppliers):
    st.markdown("#### Add supplier")
    with st.form("proc_supplier_form", clear_on_submit=True):
        name = st.text_input("Supplier / vendor name")
        contact = st.text_input("Phone, email or contact details (optional)")
        notes = st.text_input("Notes (optional)")
        save = st.form_submit_button("Add supplier")
    if save:
        if not name.strip():
            st.error("Enter a supplier name.")
        else:
            try:
                with services.db.connect() as conn:
                    conn.execute("INSERT INTO suppliers(project_id,name,contact,notes) VALUES(?,?,?,?)",
                                 (project_id, name.strip(), contact.strip(), notes.strip()))
            except Exception as exc:
                st.error(f"Supplier was not saved. The name may already exist. Details: {exc}")
            else:
                st.success("Supplier added.")
                st.rerun()

    suppliers = _suppliers(services, project_id)
    if suppliers and materials:
        st.markdown("#### Link supplier to material and set lead time")
        slabels = {s["id"]: s["name"] for s in suppliers}
        mlabels = {m["id"]: f'{m["name"]} ({m["unit"]})' for m in materials}
        with st.form("proc_supplier_material_form"):
            sid = st.selectbox("Supplier", list(slabels), format_func=lambda x: slabels[x])
            mid = st.selectbox("Material supplied", list(mlabels), format_func=lambda x: mlabels[x])
            lead = st.number_input("Lead time (calendar days)", min_value=0, max_value=365, value=7)
            link = st.form_submit_button("Save supplier lead time")
        if link:
            with services.db.connect() as conn:
                conn.execute("""INSERT INTO supplier_materials(supplier_id,material_id,lead_time_days)
                    VALUES(?,?,?) ON CONFLICT(supplier_id,material_id) DO UPDATE SET
                    lead_time_days=excluded.lead_time_days""", (sid, mid, int(lead)))
            st.success("Supplier lead time saved.")
            st.rerun()
    elif not suppliers:
        st.info("Add at least one supplier to record vendor details.")
    rows = _rows(services.db, """SELECT s.name AS supplier,s.contact,m.name AS material,
        sm.lead_time_days AS lead_time_days
        FROM supplier_materials sm JOIN suppliers s ON s.id=sm.supplier_id
        JOIN materials m ON m.id=sm.material_id WHERE s.project_id=? ORDER BY s.name,m.name""",
        (project_id,))
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_orders(services, project_id, materials, suppliers):
    st.markdown("#### Create or record a purchase order")
    if not materials or not suppliers:
        st.info("Add at least one material and one supplier before creating a purchase order.")
        return
    mlabels = {m["id"]: f'{m["name"]} ({m["unit"]})' for m in materials}
    slabels = {s["id"]: s["name"] for s in suppliers}
    with st.form("proc_order_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        mid = c1.selectbox("Material", list(mlabels), format_func=lambda x: mlabels[x])
        sid = c2.selectbox("Supplier", list(slabels), format_func=lambda x: slabels[x])
        c3, c4 = st.columns(2)
        qty = c3.number_input("Ordered quantity", min_value=0.001, value=1.0, step=1.0)
        received = c4.number_input("Quantity already received", min_value=0.0, value=0.0, step=1.0)
        c5, c6 = st.columns(2)
        order_date = c5.date_input("Order date", value=date.today(), key="new_po_order_date")
        expected = c6.date_input("Expected delivery date", value=date.today() + timedelta(days=7), key="new_po_delivery_date")
        status = st.selectbox("Status", STATUSES, index=1, key="new_po_status")
        notes = st.text_input("Notes (optional)", key="new_po_notes")
        save = st.form_submit_button("Save purchase order")
    if save:
        if received > qty:
            st.error("Received quantity cannot exceed ordered quantity.")
        elif expected < order_date:
            st.error("Expected delivery cannot be before the order date.")
        elif status == "Delivered" and received < qty:
            st.error("Mark an order Delivered only when the full quantity has arrived.")
        else:
            try:
                with services.db.connect() as conn:
                    conn.execute("""INSERT INTO purchase_orders(project_id,material_id,supplier_id,quantity,
                        received_quantity,order_date,expected_delivery,status,notes)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (project_id, mid, sid, float(qty), float(received), order_date.isoformat(),
                         expected.isoformat(), status, notes.strip()))
            except Exception as exc:
                st.error(f"Purchase order was not saved: {exc}")
            else:
                st.success("Purchase order saved.")
                st.rerun()

    rows = _rows(services.db, """SELECT po.id,po.material_id,po.supplier_id,m.name AS material,m.unit,
        s.name AS supplier,po.quantity,po.received_quantity,po.order_date,po.expected_delivery,
        po.status,po.notes
        FROM purchase_orders po JOIN materials m ON m.id=po.material_id
        JOIN suppliers s ON s.id=po.supplier_id WHERE po.project_id=? ORDER BY po.expected_delivery,po.id""",
        (project_id,))
    st.markdown("#### Purchase order register")
    if not rows:
        st.info("No purchase orders recorded yet.")
        return
    display_rows = [{k: v for k, v in row.items() if k not in ("material_id", "supplier_id")} for row in rows]
    st.dataframe(pd.DataFrame(display_rows), hide_index=True, use_container_width=True)
    labels = {r["id"]: f'PO #{r["id"]} — {r["material"]}, {r["status"]}' for r in rows}
    selected = st.selectbox("Purchase order to edit", list(labels), format_func=lambda x: labels[x], key="edit_po_select")
    current = next(r for r in rows if r["id"] == selected)
    st.markdown("#### Edit selected purchase order")
    with st.form(f"update_po_{selected}"):
        c1, c2 = st.columns(2)
        new_mid = c1.selectbox("Material", list(mlabels), index=list(mlabels).index(current["material_id"]),
                               format_func=lambda x: mlabels[x])
        new_sid = c2.selectbox("Supplier", list(slabels), index=list(slabels).index(current["supplier_id"]),
                               format_func=lambda x: slabels[x])
        c3, c4 = st.columns(2)
        new_qty = c3.number_input("Ordered quantity", min_value=0.001, value=float(current["quantity"]), step=1.0)
        new_received = c4.number_input("Total quantity received to date", min_value=0.0,
            max_value=max(float(current["quantity"]), float(current["received_quantity"])),
            value=float(current["received_quantity"]), step=1.0)
        c5, c6 = st.columns(2)
        current_order_date = date.fromisoformat(current["order_date"])
        current_delivery_date = date.fromisoformat(current["expected_delivery"])
        new_order_date = c5.date_input("Order date", value=current_order_date, key=f"edit_po_order_date_{selected}")
        new_expected = c6.date_input("Expected delivery date", value=current_delivery_date, key=f"edit_po_delivery_date_{selected}")
        new_status = st.selectbox("Status", STATUSES, index=STATUSES.index(current["status"]), key=f"edit_po_status_{selected}")
        new_notes = st.text_input("Notes", value=current["notes"], key=f"edit_po_notes_{selected}")
        update = st.form_submit_button("Save purchase-order changes")
    if update:
        if new_received > new_qty:
            st.error("Received quantity cannot exceed ordered quantity.")
        elif new_expected < new_order_date:
            st.error("Expected delivery cannot be before the order date.")
        elif new_status == "Delivered" and new_received < new_qty:
            st.error("Mark an order Delivered only when the full quantity has arrived.")
        else:
            with services.db.connect() as conn:
                conn.execute("""UPDATE purchase_orders
                    SET material_id=?,supplier_id=?,quantity=?,received_quantity=?,order_date=?,
                        expected_delivery=?,status=?,notes=?
                    WHERE id=? AND project_id=?""",
                    (new_mid, new_sid, float(new_qty), float(new_received), new_order_date.isoformat(),
                     new_expected.isoformat(), new_status, new_notes.strip(), selected, project_id))
            st.success(f"Purchase order #{selected} updated.")
            st.rerun()
    st.caption("Cancelled orders remain in the register for audit history and do not count as incoming stock.")


def _render_price_comparison(services, project_id, materials, suppliers):
    st.markdown("#### Record a supplier quotation")
    if not materials or not suppliers:
        st.info("Add at least one material and one supplier before recording quotations.")
        return
    mlabels = {m["id"]: f'{m["name"]} ({m["unit"]})' for m in materials}
    slabels = {s["id"]: s["name"] for s in suppliers}
    with st.form("proc_quote_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        mid = c1.selectbox("Material", list(mlabels), format_func=lambda x: mlabels[x])
        sid = c2.selectbox("Supplier", list(slabels), format_func=lambda x: slabels[x])
        c3, c4 = st.columns(2)
        price = c3.number_input("Quoted price per unit (₹)", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        quote_date = c4.date_input("Quote date", value=date.today(), key="quote_date")
        valid_until = st.date_input("Quote valid until", value=date.today() + timedelta(days=30), key="quote_valid_until")
        notes = st.text_input("Quote notes (optional)", key="quote_notes")
        save = st.form_submit_button("Save quotation")
    if save:
        if valid_until < quote_date:
            st.error("Quote validity date cannot be before the quote date.")
        else:
            with services.db.connect() as conn:
                conn.execute("""INSERT INTO supplier_quotes
                    (project_id,material_id,supplier_id,unit_price,currency,quote_date,valid_until,notes)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (project_id, mid, sid, float(price), "INR", quote_date.isoformat(),
                     valid_until.isoformat(), notes.strip()))
            st.success("Supplier quotation saved.")
            st.rerun()

    quotes = _rows(services.db, """SELECT q.id,m.id AS material_id,m.name AS material,m.unit,s.name AS supplier,
        q.unit_price,q.currency,q.quote_date,q.valid_until,q.notes
        FROM supplier_quotes q JOIN materials m ON m.id=q.material_id
        JOIN suppliers s ON s.id=q.supplier_id
        WHERE q.project_id=? ORDER BY m.name,q.unit_price,s.name""", (project_id,))
    st.markdown("#### Saved quotations")
    if not quotes:
        st.info("No quotations recorded yet.")
        return
    quote_df = pd.DataFrame(quotes)
    st.dataframe(quote_df.drop(columns=["id", "material_id"]), hide_index=True, use_container_width=True)
    st.markdown("#### Compare prices against project requirements")
    requirements = _rows(services.db, """SELECT material_id,SUM(required_quantity) AS required_quantity
        FROM activity_materials WHERE project_id=? GROUP BY material_id""", (project_id,))
    required_by_material = {r["material_id"]: float(r["required_quantity"]) for r in requirements}
    today = date.today().isoformat()
    comparison = []
    for q in quotes:
        qty = required_by_material.get(q["material_id"], 0.0)
        comparison.append({
            "Material": q["material"], "Supplier": q["supplier"], "Unit": q["unit"],
            "Quoted price (₹/unit)": float(q["unit_price"]),
            "Requirement quantity": qty, "Estimated total (₹)": round(qty * float(q["unit_price"]), 2),
            "Quote date": q["quote_date"], "Valid until": q["valid_until"],
            "Quote status": "Valid" if q["valid_until"] >= today else "Expired",
        })
    compare_df = pd.DataFrame(comparison)
    st.dataframe(compare_df, hide_index=True, use_container_width=True)
    valid_quotes = compare_df[compare_df["Quote status"] == "Valid"]
    if not valid_quotes.empty:
        valid_with_qty = valid_quotes[valid_quotes["Requirement quantity"] > 0]
        if not valid_with_qty.empty:
            cheapest = valid_with_qty.sort_values(["Material", "Quoted price (₹/unit)"]).groupby("Material", as_index=False).first()
            st.markdown("#### Lowest valid quoted price by material")
            st.dataframe(cheapest[["Material", "Supplier", "Quoted price (₹/unit)", "Requirement quantity",
                                   "Estimated total (₹)"]], hide_index=True, use_container_width=True)
    st.caption("Price comparisons use manually entered quotations. They are not live market prices. Check taxes, transport, quality/specification, minimum order quantities and quote validity before purchasing.")


def _render_reports(services, project_id):
    st.markdown("#### Download procurement reports")
    report_type = st.selectbox("Report", [
        "Material requirements", "Inventory", "Purchase orders", "Supplier quotations", "Procurement coverage"
    ], key="proc_report_type")
    report_queries = {
        "Material requirements": ("""SELECT a.code AS activity_code,a.name AS activity,m.name AS material,
            am.required_quantity AS required_quantity,m.unit,am.notes
            FROM activity_materials am JOIN activities a ON a.id=am.activity_id
            JOIN materials m ON m.id=am.material_id WHERE am.project_id=?
            ORDER BY a.id,m.name""", (project_id,)),
        "Inventory": ("""SELECT m.name AS material,m.unit,COALESCE(i.available_quantity,0) AS physical_stock,
            COALESCE(i.reserved_quantity,0) AS reserved,
            MAX(0,COALESCE(i.available_quantity,0)-COALESCE(i.reserved_quantity,0)) AS usable_stock,
            i.updated_at AS last_updated FROM materials m LEFT JOIN inventory i ON i.material_id=m.id
            WHERE m.project_id=? ORDER BY m.name""", (project_id,)),
        "Purchase orders": ("""SELECT po.id AS order_id,m.name AS material,m.unit,s.name AS supplier,
            po.quantity AS ordered_quantity,po.received_quantity,po.order_date,po.expected_delivery,
            po.status,po.notes FROM purchase_orders po JOIN materials m ON m.id=po.material_id
            JOIN suppliers s ON s.id=po.supplier_id WHERE po.project_id=? ORDER BY po.id""", (project_id,)),
        "Supplier quotations": ("""SELECT m.name AS material,m.unit,s.name AS supplier,q.unit_price,q.currency,
            q.quote_date,q.valid_until,q.notes FROM supplier_quotes q JOIN materials m ON m.id=q.material_id
            JOIN suppliers s ON s.id=q.supplier_id WHERE q.project_id=? ORDER BY m.name,q.unit_price""", (project_id,)),
    }
    if report_type == "Procurement coverage":
        try:
            schedule = services.schedule.calculate_schedule(project_id)
            activity_by_id = {a.activity_id: a for a in schedule.activities}
        except BuildOSError as exc:
            show_error(exc)
            return
        requirements = _rows(services.db, """SELECT am.material_id,m.name AS material,m.unit,
            SUM(am.required_quantity) AS required_quantity FROM activity_materials am
            JOIN materials m ON m.id=am.material_id WHERE am.project_id=?
            GROUP BY am.material_id,m.name,m.unit ORDER BY m.name""", (project_id,))
        po_rows = _rows(services.db, "SELECT * FROM purchase_orders WHERE project_id=?", (project_id,))
        inv_rows = _rows(services.db, """SELECT i.* FROM inventory i JOIN materials m ON m.id=i.material_id
            WHERE m.project_id=?""", (project_id,))
        inventory = {r["material_id"]: r for r in inv_rows}
        out = []
        for r in requirements:
            relevant = _rows(services.db, """SELECT activity_id FROM activity_materials
                WHERE project_id=? AND material_id=?""", (project_id, r["material_id"]))
            need_dates = [activity_by_id[x["activity_id"]].es_date for x in relevant
                          if x["activity_id"] in activity_by_id]
            if not need_dates:
                continue
            need = min(need_dates)
            inv = inventory.get(r["material_id"], {})
            usable = max(0.0, float(inv.get("available_quantity", 0))-float(inv.get("reserved_quantity", 0)))
            incoming = sum(outstanding_order_quantity(po["quantity"],po["received_quantity"],po["status"])
                for po in po_rows if po["material_id"] == r["material_id"]
                and po["expected_delivery"] <= need.isoformat())
            out.append({"Material":r["material"],"Unit":r["unit"],"Required":float(r["required_quantity"]),
                        "Usable stock":usable,"Eligible incoming by need date":incoming,
                        "Net to purchase":net_purchase_quantity(r["required_quantity"],usable,0,incoming),
                        "Need date":need.isoformat()})
        df = pd.DataFrame(out)
    else:
        query, params = report_queries[report_type]
        df = pd.DataFrame(_rows(services.db, query, params))
    if df.empty:
        st.info("No records are available for this report yet. Add the relevant procurement data first.")
        return
    st.dataframe(df, hide_index=True, use_container_width=True)
    safe_name = report_type.lower().replace(" ", "_")
    st.download_button("Download CSV", data=df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"buildos_{safe_name}.csv", mime="text/csv")
    try:
        import io
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Procurement")
        st.download_button("Download Excel (.xlsx)", data=buffer.getvalue(),
                           file_name=f"buildos_{safe_name}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except ImportError:
        st.info("Excel export requires openpyxl. CSV export is still available.")

def _render_dashboard(services, project_id, activity_by_id, materials, suppliers):
    st.markdown("#### Procurement overview")
    if not materials:
        st.info("Start by adding materials and linking them to activities in the Material requirements tab.")
        return
    requirements = _rows(services.db, """SELECT am.material_id, m.name AS material,m.unit,
        SUM(am.required_quantity) AS required_quantity, MIN(a.id) AS first_activity_id
        FROM activity_materials am JOIN materials m ON m.id=am.material_id
        JOIN activities a ON a.id=am.activity_id
        WHERE am.project_id=? GROUP BY am.material_id,m.name,m.unit ORDER BY m.name""", (project_id,))
    inventory = {r["material_id"]: r for r in _rows(services.db,
        "SELECT material_id,available_quantity,reserved_quantity FROM inventory")}
    po_rows = _rows(services.db, "SELECT * FROM purchase_orders WHERE project_id=?", (project_id,))
    supplier_links = _rows(services.db, """SELECT sm.material_id,sm.lead_time_days,s.name AS supplier
        FROM supplier_materials sm JOIN suppliers s ON s.id=sm.supplier_id WHERE s.project_id=?""",
        (project_id,))
    links_by_material = {}
    for link in supplier_links:
        links_by_material.setdefault(link["material_id"], []).append(link)

    today = date.today()
    output = []
    for req in requirements:
        # Need date is the earliest scheduled start of any activity using this material.
        relevant = _rows(services.db, """SELECT activity_id FROM activity_materials
            WHERE project_id=? AND material_id=?""", (project_id, req["material_id"]))
        dates = [activity_by_id[r["activity_id"]].es_date for r in relevant if r["activity_id"] in activity_by_id]
        if not dates:
            continue
        need = min(dates)
        inv = inventory.get(req["material_id"], {})
        usable = max(0.0, float(inv.get("available_quantity", 0)) - float(inv.get("reserved_quantity", 0)))
        incoming = 0.0
        for po in po_rows:
            if po["material_id"] == req["material_id"] and po["expected_delivery"] <= need.isoformat():
                incoming += outstanding_order_quantity(po["quantity"], po["received_quantity"], po["status"])
        net = net_purchase_quantity(req["required_quantity"], usable, 0, incoming)
        link = (links_by_material.get(req["material_id"]) or [{}])[0]
        lead = int(link.get("lead_time_days", 7))
        order_date = recommended_order_date(need, lead, 2)
        if net <= 0:
            alert = "Covered"
        elif any(po["material_id"] == req["material_id"] and po["status"] in ("Ordered", "Partially delivered")
                 and po["expected_delivery"] > need.isoformat() for po in po_rows):
            alert = "Delivery after need date"
        elif order_date < today:
            alert = "Order overdue"
        elif order_date <= today + timedelta(days=7):
            alert = "Order due within 7 days"
        else:
            alert = "Plan purchase"
        output.append({
            "Material": req["material"], "Required": round(float(req["required_quantity"]), 3),
            "Unit": req["unit"], "Usable stock": round(usable, 3),
            "Eligible incoming by need date": round(incoming, 3), "Net to purchase": round(net, 3),
            "Need date": need.isoformat(), "Recommended order date": order_date.isoformat(),
            "Supplier lead time (days)": lead, "Alert": alert,
        })
    if not output:
        st.info("Add material requirements linked to scheduled activities to see procurement calculations.")
        return
    df = pd.DataFrame(output)
    col1, col2, col3 = st.columns(3)
    col1.metric("Materials tracked", len(df))
    col2.metric("Materials with shortage", int((df["Net to purchase"] > 0).sum()))
    col3.metric("Orders overdue / due soon", int(df["Alert"].isin(["Order overdue", "Order due within 7 days", "Delivery after need date"]).sum()))
    urgent = df[df["Alert"] != "Covered"]
    if not urgent.empty:
        st.markdown("#### Items needing attention")
        st.dataframe(urgent, hide_index=True, use_container_width=True)
    st.markdown("#### All material coverage")
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(
        "Rules: need date is the earliest CPM start date among activities using a material. "
        "Only Ordered/Partially delivered quantities arriving by that date count as incoming. "
        "Recommended order date = need date − supplier lead time − 2-day buffer. "
        "Demo data has no material quantities; enter project-specific estimates. Validate quantities and units before purchasing."
    )
