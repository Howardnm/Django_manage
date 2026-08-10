from django.urls import path
from .views.HomeView import HomeView
from .views.ProjectOverviewView import ProjectOverviewView
from .views.ProjectStatisticsView import ProjectStatisticsView
from .views.CustomerActivityView import CustomerActivityOverviewView
from .views.PersonalWorkspaceView import PersonalWorkspaceView
from .views.SystemOverviewView import SystemOverviewView
from .views.SchedulingCalendarView import SchedulingCalendarView
from .views.SchedulingCalendarEventsView import SchedulingCalendarEventsView

urlpatterns = [
    # 首页（纯静态系统介绍）
    path('', HomeView.as_view(), name='panel_home'),

    # 个人工作台
    path('workspace/', PersonalWorkspaceView.as_view(), name='personal_workspace'),

    # 系统总览
    path('system-overview/', SystemOverviewView.as_view(), name='system_overview'),

    # 项目看板
    path('project-overview/', ProjectOverviewView.as_view(), name='project_overview'),
    path('project-statistics/', ProjectStatisticsView.as_view(), name='project_statistics'),

    # 客户行为分析
    path('customer-activity/', CustomerActivityOverviewView.as_view(), name='customer_activity_overview'),

    # 只读排产日历（看板工作台）
    path('scheduling-calendar/', SchedulingCalendarView.as_view(), name='scheduling_calendar'),
    path('scheduling-calendar/events/', SchedulingCalendarEventsView.as_view(), name='scheduling_calendar_events'),
]
