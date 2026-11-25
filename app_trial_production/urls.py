from django.urls import path
from .views.ProductionOrder import (
    ProductionOrderDetailView, ProductionOrderCreateView,
    ProductionOrderUpdateView, ProductionOrderInitiateView,
    ProductionOrderStartWorkflowView, ProductionOrderStartExtrusionView,
    ProductionOrderDeleteView, ProductionOrderPrintView,
)
from .views.Dashboard import TrialDashboardView
from .views.ExtrusionBoard import ExtrusionBoardView
from .views.ExtrusionBoardApi import (
    ExtrusionScheduleApiView,
    ExtrusionUnscheduleApiView, ExtrusionEventsApiView,
    ExtrusionStatsApiView, PendingOrdersCardView,
)
from .views.ExtrusionTask import (
    ExtrusionTaskListView, ExtrusionTaskDetailView,
    ExtrusionTaskStartView, ExtrusionRecordFormView,
)
from .views.PelletSplit import PelletSplitView
from .views.Autocomplete import TrialAutocompleteView
from .views.process_profile_params import ProcessProfileParamsView
from .views.SchedulingCalendar import SchedulingCalendarView
from .views.SchedulingCalendarApi import SchedulingCalendarEventsView

urlpatterns = [
    # Dashboard
    path('', TrialDashboardView.as_view(), name='trial_dashboard'),

    # Production Orders
    path('orders/create/', ProductionOrderCreateView.as_view(), name='trial_order_create'),
    path(
        'orders/process-profiles/<int:pk>/params/',
        ProcessProfileParamsView.as_view(),
        name='trial_process_profile_params',
    ),
    path('orders/initiate/', ProductionOrderInitiateView.as_view(), name='trial_order_initiate'),
    path('orders/<int:pk>/', ProductionOrderDetailView.as_view(), name='trial_order_detail'),
    path('orders/<int:pk>/print/', ProductionOrderPrintView.as_view(), name='trial_order_print'),
    path('orders/<int:pk>/edit/', ProductionOrderUpdateView.as_view(), name='trial_order_edit'),
    path('orders/<int:pk>/delete/', ProductionOrderDeleteView.as_view(), name='trial_order_delete'),
    path('orders/<int:pk>/start-workflow/', ProductionOrderStartWorkflowView.as_view(), name='trial_order_start_workflow'),
    path('orders/<int:pk>/start-extrusion/', ProductionOrderStartExtrusionView.as_view(), name='trial_order_start_extrusion'),

    # Extrusion Board (排产工作台)
    path('extrusion-board/', ExtrusionBoardView.as_view(), name='trial_extrusion_board'),
    path('extrusion-board/events/', ExtrusionEventsApiView.as_view(), name='trial_extrusion_board_events'),
    path('extrusion-board/pending-card/', PendingOrdersCardView.as_view(), name='trial_extrusion_board_pending_card'),
    path('extrusion-board/stats/', ExtrusionStatsApiView.as_view(), name='trial_extrusion_board_stats'),
    path('extrusion-board/schedule/', ExtrusionScheduleApiView.as_view(), name='trial_extrusion_schedule'),
    path('extrusion-board/<int:pk>/unschedule/', ExtrusionUnscheduleApiView.as_view(), name='trial_extrusion_board_unschedule'),

    # Extrusion Task
    path('extrusion-tasks/', ExtrusionTaskListView.as_view(), name='trial_extrusion_task_list'),
    path('orders/<int:pk>/extrusion/', ExtrusionTaskDetailView.as_view(), name='trial_extrusion_detail'),
    path('orders/<int:pk>/extrusion/start/', ExtrusionTaskStartView.as_view(), name='trial_extrusion_start'),
    path('orders/<int:pk>/extrusion/record/', ExtrusionRecordFormView.as_view(), name='trial_extrusion_record'),

    # Pellet Split (挤出后颗粒分拨)
    path('orders/<int:pk>/split/', PelletSplitView.as_view(), name='trial_pellet_split'),

    # Readonly Scheduling Calendar (只读排产日历)
    path('calendar/', SchedulingCalendarView.as_view(), name='trial_scheduling_calendar'),
    path('calendar/events/', SchedulingCalendarEventsView.as_view(), name='trial_scheduling_calendar_events'),

    # API
    path('api/search/', TrialAutocompleteView.as_view(), name='trial_api_search'),
]
