"""
SQLAlchemy Table 정의 — Django가 관리하는 테이블을 그대로 사용.
마이그레이션은 Django 쪽에서만 수행하며 여기서는 읽기/쓰기만 담당.
"""
from sqlalchemy import (
    Table, Column, Integer, String, Boolean, DateTime, MetaData, ForeignKey
)

metadata = MetaData()

slack_workspace = Table(
    'slack_app_slackworkspace', metadata,
    Column('id', Integer, primary_key=True),
    Column('team_id', String, unique=True),
    Column('team_name', String),
    Column('bot_token', String),
    Column('status', String),                                    # pending / approved / rejected
    Column('customer_id', Integer, ForeignKey('customer_customer.id'), nullable=True),
    Column('created_at', DateTime(timezone=True)),
    Column('updated_at', DateTime(timezone=True)),
)

subscription = Table(
    'subscriber_subscription', metadata,
    Column('id', Integer, primary_key=True),
    Column('customer_id', Integer, ForeignKey('customer_customer.id')),
    Column('solution_id', Integer, ForeignKey('product_solution.id')),
    Column('channel', String),                                   # email / slack
    Column('is_active', Boolean),
    Column('frequency', String),                                 # weekly / monthly / quarterly
    Column('max_items', Integer),
    Column('slack_channel', String, nullable=True),
    Column('created_at', DateTime(timezone=True)),
    Column('updated_at', DateTime(timezone=True)),
)

solution = Table(
    'product_solution', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
)

customer = Table(
    'customer_customer', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
)

# Customer ↔ Solution ManyToMany (Django 자동 생성 테이블)
customer_solutions = Table(
    'customer_customer_solutions', metadata,
    Column('id', Integer, primary_key=True),
    Column('customer_id', Integer, ForeignKey('customer_customer.id')),
    Column('solution_id', Integer, ForeignKey('product_solution.id')),
)
