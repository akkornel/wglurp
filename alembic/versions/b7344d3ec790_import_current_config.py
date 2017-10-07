"""Import current config

Revision ID: b7344d3ec790
Revises: None ('initial' config)
Create Date: 2017-10-07 16:25:30.153212-07:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b7344d3ec790'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE SEQUENCE changes_id_seq')
    op.create_table('changes',
        sa.Column('id', sa.BigInteger(), server_default=sa.text("nextval('changes_id_seq')"), nullable=False),
        sa.Column('worker', sa.SmallInteger(), nullable=False),
        sa.Column('action', sa.Enum('ADD', 'REMOVE', 'SYNC', 'FLUSH_CHANGES', 'FLUSH_ALL', 'WAIT', name='changes_action_enum'), nullable=False),
        sa.Column('group', sa.String(), nullable=True),
        sa.Column('data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('changes_pk'))
    )
    op.create_index('changes_worker_id_idx', 'changes', ['worker', 'id'], unique=False)

    op.execute('CREATE SEQUENCE destinations_id_seq')
    op.create_table('destinations',
        sa.Column('id', sa.Integer(), server_default=sa.text("nextval('destinations_id_seq')"), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'DEFER', 'DISABLE', name='destinations_status_enum'), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('challenge_seed', sa.Binary(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('destinations_pk'))
    )
    op.create_index(op.f('destinations_status_idx'), 'destinations', ['status'], unique=False)

    op.execute('CREATE SEQUENCE challenges_id_seq')
    op.create_table('challenges',
        sa.Column('id', sa.BigInteger(), server_default=sa.text("nextval('challenges_id_seq')"), nullable=False),
        sa.Column('destination_id', sa.Integer(), nullable=False),
        sa.Column('nonce', sa.Binary(), nullable=False),
        sa.Column('challenge', sa.Binary(), nullable=False),
        sa.Column('expiration', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['destination_id'], ['destinations.id'], name=op.f('challenges_destination_id_fk_destinations_id'), onupdate='CASCADE', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('challenges_pk'))
    )
    op.create_index(op.f('challenges_expiration_idx'), 'challenges', ['expiration'], unique=False)

    op.create_table('destinations_sqs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['destinations.id'], name=op.f('destinations_sqs_id_fk_destinations_id'), onupdate='CASCADE', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('destinations_sqs_pk'))
    )

    op.execute('CREATE SEQUENCE updates_id_seq')
    op.create_table('updates',
        sa.Column('id', sa.BigInteger(), server_default=sa.text("nextval('updates_id_seq')"), nullable=False),
        sa.Column('destination_id', sa.Integer(), nullable=True),
        sa.Column('message', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['destination_id'], ['destinations.id'], name=op.f('updates_destination_id_fk_destinations_id'), onupdate='CASCADE', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('updates_pk'))
    )
    op.create_index('updates_destination_id_idx', 'updates', ['destination_id', 'id'], unique=False)


def downgrade():
    op.drop_index('updates_destination_id_idx', table_name='updates')
    op.drop_table('updates')
    op.execute('DROP SEQUENCE updates_id_seq')
    op.drop_table('destinations_sqs')
    op.drop_index(op.f('challenges_expiration_idx'), table_name='challenges')
    op.drop_table('challenges')
    op.execute('DROP SEQUENCE challenges_id_seq')
    op.drop_index(op.f('destinations_status_idx'), table_name='destinations')
    op.drop_table('destinations')
    op.execute('DROP SEQUENCE destinations_id_seq')
    op.drop_index('changes_worker_id_idx', table_name='changes')
    op.drop_table('changes')
    op.execute('DROP SEQUENCE changes_id_seq')
