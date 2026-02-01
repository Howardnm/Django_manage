from django.urls import path
from .views.ProjectOverviewView import ProjectOverviewView
from .views.HomeView import HomeView
from .views.MaterialLibraryView import MaterialLibraryView
from .views.FormulaLibraryView import FormulaLibraryView
from .views.ProcessLibraryView import ProcessLibraryView
from .views.RawMaterialLibraryView import RawMaterialLibraryView


urlpatterns = [
    path('', HomeView.as_view(), name='panel_home'),
    path('project-overview/', ProjectOverviewView.as_view(), name='project_overview'),
    path('material-library/', MaterialLibraryView.as_view(), name='material_library'),
    path('formula-library/', FormulaLibraryView.as_view(), name='formula_library'),
    path('process-library/', ProcessLibraryView.as_view(), name='process_library'),
    path('raw-material-library/', RawMaterialLibraryView.as_view(), name='raw_material_library'),
]
