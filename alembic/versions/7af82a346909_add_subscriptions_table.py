"""Add subscriptions table

Revision ID: 7af82a346909
Revises: b7344d3ec790
Create Date: 2017-10-07 22:30:19.116476-07:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7af82a346909'
down_revision = 'b7344d3ec790'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE SEQUENCE subscriptions_id_seq')
    op.create_table('subscriptions',
        sa.Column('id', sa.BigInteger(), server_default=sa.text("nextval('subscriptions_id_seq')"), nullable=False),
        sa.Column('string', sa.String(), nullable=False),
        sa.Column('type', sa.Enum('PREFIX', 'SINGLE', name='subscriptions_type_enum'), nullable=False),
        sa.Column('destination_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['destination_id'], ['destinations.id'], name=op.f('subscriptions_destination_id_fk_destinations_id'), onupdate='CASCADE', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('subscriptions_pk'))
    )
    op.create_index('subscriptions_destination_string_type_uidx', 'subscriptions', ['destination_id', 'string', 'type'], unique=True)
    op.create_index('subscriptions_type_string_idx', 'subscriptions', ['type', 'string'], unique=False)


def downgrade():
    op.drop_index('subscriptions_type_string_idx', table_name='subscriptions')
    op.drop_index('subscriptions_destination_string_type_uidx', table_name='subscriptions')
    op.drop_table('subscriptions')
    op.execute('DROP SEQUENCE subscriptions_id_seq')
