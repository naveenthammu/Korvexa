"""inventory recipes and fulfillment movements

Revision ID: 20260704_0002
Revises: 20260703_0001
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "20260704_0002"
down_revision = "20260703_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_recipes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("inventory_item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
        sa.Column("quantity_per_unit", sa.Numeric(12, 3), nullable=False),
        sa.Column("wastage_percent", sa.Numeric(5, 2), server_default="0.00"),
        sa.Column("active", sa.Boolean(), server_default="1"),
        sa.UniqueConstraint("product_id", "inventory_item_id", name="uq_product_recipe_item"),
    )
    op.create_index("ix_product_recipes_tenant_id", "product_recipes", ["tenant_id"])
    op.create_index("ix_product_recipes_branch_id", "product_recipes", ["branch_id"])
    op.create_index("ix_product_recipes_product_id", "product_recipes", ["product_id"])
    op.create_index("ix_product_recipes_inventory_item_id", "product_recipes", ["inventory_item_id"])

    with op.batch_alter_table("stock_movements") as batch_op:
        batch_op.add_column(sa.Column("order_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key("fk_stock_movements_order_id_orders", "orders", ["order_id"], ["id"])
        batch_op.create_index("ix_stock_movements_order_id", ["order_id"])


def downgrade() -> None:
    with op.batch_alter_table("stock_movements") as batch_op:
        batch_op.drop_index("ix_stock_movements_order_id")
        batch_op.drop_constraint("fk_stock_movements_order_id_orders", type_="foreignkey")
        batch_op.drop_column("order_id")

    op.drop_index("ix_product_recipes_inventory_item_id", table_name="product_recipes")
    op.drop_index("ix_product_recipes_product_id", table_name="product_recipes")
    op.drop_index("ix_product_recipes_branch_id", table_name="product_recipes")
    op.drop_index("ix_product_recipes_tenant_id", table_name="product_recipes")
    op.drop_table("product_recipes")
