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

    dash, req, stock, supp, orders = st.tabs(
        ["Overview & alerts", "Material requirements", "Inventory", "Suppliers", "Purchase orders"]
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
        order_date = c5.date_input("Order date", value=date.today())
        expected = c6.date_input("Expected delivery date", value=date.today() + timedelta(days=7))
        status = st.selectbox("Status", STATUSES, index=1)
        notes = st.text_input("Notes (optional)")
        save = st.form_submit_button("Save purchase order")
    if save:
        if received > qty:
            st.error("Received quantity cannot exceed ordered quantity.")
        elif expected < order_date:
            st.error("Expected delivery cannot be before the order date.")
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
    rows = _rows(services.db, """SELECT po.id,m.name AS material,m.unit,s.name AS supplier,
        po.quantity,po.received_quantity,po.order_date,po.expected_delivery,po.status,po.notes
        FROM purchase_orders po JOIN materials m ON m.id=po.material_id
        JOIN suppliers s ON s.id=po.supplier_id WHERE po.project_id=? ORDER BY po.expected_delivery,po.id""",
        (project_id,))
    st.markdown("#### Purchase order register")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        labels = {r["id"]: f'PO #{r["id"]} — {r["material"]}, {r["status"]}' for r in rows}
        selected = st.selectbox("Purchase order to update", list(labels), format_func=lambda x: labels[x])
        current = next(r for r in rows if r["id"] == selected)
        with st.form(f"update_po_{selected}"):
            new_status = st.selectbox("Updated status", STATUSES, index=STATUSES.index(current["status"]))
            new_received = st.number_input("Total quantity received to date", min_value=0.0,
                max_value=float(current["quantity"]), value=float(current["received_quantity"]), step=1.0)
            update = st.form_submit_button("Update purchase order")
        if update:
            if new_status == "Delivered" and new_received < float(current["quantity"]):
                st.error("Mark an order Delivered only when the full quantity has arrived.")
            else:
                with services.db.connect() as conn:
                    conn.execute("UPDATE purchase_orders SET status=?,received_quantity=? WHERE id=?",
                                 (new_status, float(new_received), selected))
                st.success("Purchase order updated.")
                st.rerun()
    else:
        st.info("No purchase orders recorded yet.")


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
