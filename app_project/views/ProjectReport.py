import io
from datetime import datetime
from django.http import HttpResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from app_project.models import Project
from app_project.mixins import ProjectPermissionMixin

class ProjectReportExportView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_project.view_project'

    def get(self, request, pk):
        # 1. 获取项目对象并检查权限
        project = get_object_or_404(Project.objects.select_related(
            'manager',
            'repository',
            'repository__customer',
            'repository__oem',
            'repository__material',
            'repository__salesperson'
        ).prefetch_related('nodes'), pk=pk)
        
        self.check_project_permission(project)

        # 2. 创建 Word 文档
        document = Document()
        
        # 设置中文字体兼容
        document.styles['Normal'].font.name = u'微软雅黑'
        document.styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), u'微软雅黑')

        # --- 封面 ---
        self._add_cover(document, project)
        
        document.add_page_break()

        # --- 第一章：项目概况 ---
        self._add_chapter_overview(document, project)

        # --- 第二章：商业与产品信息 ---
        self._add_chapter_business(document, project)

        # --- 第三章：材料方案 ---
        self._add_chapter_material(document, project)

        # --- 第四章：项目进度详情 ---
        self._add_chapter_progress(document, project)

        # 3. 输出文件流
        buffer = io.BytesIO()
        document.save(buffer)
        buffer.seek(0)

        filename = f"项目进度报告_{project.name}_{datetime.now().strftime('%Y%m%d')}.docx"
        # 处理中文文件名乱码
        import urllib.parse
        filename = urllib.parse.quote(filename)

        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _add_heading(self, document, text, level=1):
        """辅助方法：添加带中文支持的标题"""
        heading = document.add_heading(text, level=level)
        for run in heading.runs:
            run.font.name = u'微软雅黑'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), u'微软雅黑')
            run.font.color.rgb = RGBColor(0, 0, 0) # 黑色标题

    def _add_paragraph(self, document, text, bold=False):
        """辅助方法：添加段落"""
        p = document.add_paragraph()
        run = p.add_run(text)
        run.font.name = u'微软雅黑'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), u'微软雅黑')
        if bold:
            run.font.bold = True
        return p

    def _add_cover(self, document, project):
        """生成封面"""
        for _ in range(5): document.add_paragraph() # 空行
        
        title = document.add_heading(project.name, 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            run.font.name = u'微软雅黑'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), u'微软雅黑')
            run.font.size = Pt(26)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0, 51, 102) # 深蓝色

        subtitle = document.add_paragraph("项目进度汇报报告")
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.runs[0]
        run.font.size = Pt(18)
        run.font.name = u'微软雅黑'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), u'微软雅黑')

        for _ in range(8): document.add_paragraph()

        # 底部信息
        info = document.add_paragraph()
        info.alignment = WD_ALIGN_PARAGRAPH.CENTER
        info_text = f"项目负责人：{project.manager.username}\n生成日期：{datetime.now().strftime('%Y-%m-%d')}"
        run = info.add_run(info_text)
        run.font.size = Pt(12)
        run.font.name = u'微软雅黑'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), u'微软雅黑')

    def _add_chapter_overview(self, document, project):
        self._add_heading(document, "1. 项目概况")
        
        table = document.add_table(rows=3, cols=2)
        table.style = 'Table Grid'
        
        # 行1
        cells = table.rows[0].cells
        cells[0].text = "项目名称"
        cells[1].text = project.name
        
        # 行2
        cells = table.rows[1].cells
        cells[0].text = "当前阶段"
        cells[1].text = project.get_current_stage_display()
        
        # 行3
        cells = table.rows[2].cells
        cells[0].text = "总体进度"
        cells[1].text = f"{project.progress_percent}%"

        # 项目描述
        self._add_heading(document, "项目背景与描述", level=2)
        desc = project.description if project.description else "暂无描述"
        self._add_paragraph(document, desc)

    def _add_chapter_business(self, document, project):
        self._add_heading(document, "2. 商业与产品信息")
        
        repo = getattr(project, 'repository', None)
        if not repo:
            self._add_paragraph(document, "暂无档案信息")
            return

        table = document.add_table(rows=4, cols=4)
        table.style = 'Table Grid'
        
        # 表头
        row0 = table.rows[0].cells
        row0[0].text = "直接客户"
        row0[1].text = repo.customer.company_name if repo.customer else "-"
        row0[2].text = "终端主机厂"
        row0[3].text = repo.oem.name if repo.oem else "-"
        
        row1 = table.rows[1].cells
        row1[0].text = "产品名称"
        row1[1].text = repo.product_name or "-"
        row1[2].text = "产品代码"
        row1[3].text = repo.product_code or "-"
        
        row2 = table.rows[2].cells
        row2[0].text = "目标成本"
        row2[1].text = f"¥{repo.target_cost}" if repo.target_cost else "-"
        row2[2].text = "竞品售价"
        row2[3].text = f"¥{repo.competitor_price}" if repo.competitor_price else "-"
        
        row3 = table.rows[3].cells
        row3[0].text = "跟进业务员"
        row3[1].text = repo.salesperson.name if repo.salesperson else "-"
        row3[2].text = "联系电话"
        row3[3].text = repo.salesperson.phone if repo.salesperson else "-"

    def _add_chapter_material(self, document, project):
        self._add_heading(document, "3. 材料方案")
        
        repo = getattr(project, 'repository', None)
        if not repo or not repo.material:
            self._add_paragraph(document, "暂未选定材料")
            return

        mat = repo.material
        self._add_paragraph(document, f"选定材料：{mat.grade_name} ({mat.manufacturer})", bold=True)
        self._add_paragraph(document, f"材料类型：{mat.category.name} | 阻燃等级：{mat.flammability}")
        
        # 性能数据表格
        self._add_heading(document, "核心性能指标", level=2)
        
        # 获取分组后的性能数据
        grouped_props = mat.get_grouped_properties()
        
        if not grouped_props:
            self._add_paragraph(document, "暂无性能数据")
        else:
            table = document.add_table(rows=1, cols=4)
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = "分类"
            hdr_cells[1].text = "指标名称"
            hdr_cells[2].text = "测试标准"
            hdr_cells[3].text = "数值"
            
            for group in grouped_props:
                for item in group['items']:
                    row_cells = table.add_row().cells
                    row_cells[0].text = group['category_name']
                    row_cells[1].text = item['name']
                    
                    std_text = item['standard']
                    if item['condition']:
                        std_text += f" ({item['condition']})"
                    row_cells[2].text = std_text
                    
                    val_text = str(item['value'])
                    if item['unit']:
                        val_text += f" {item['unit']}"
                    row_cells[3].text = val_text

    def _add_chapter_progress(self, document, project):
        self._add_heading(document, "4. 项目进度详情")
        
        table = document.add_table(rows=1, cols=4)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "阶段"
        hdr_cells[1].text = "状态"
        hdr_cells[2].text = "更新时间"
        hdr_cells[3].text = "备注/进展"
        
        # 设置列宽 (大致比例)
        for cell in table.columns[3].cells:
            cell.width = Inches(3.0)

        for node in project.cached_nodes:
            row_cells = table.add_row().cells
            
            # 阶段名 (如果是多轮，显示轮次)
            stage_name = node.get_stage_display()
            if node.round > 1:
                stage_name += f" (第{node.round}轮)"
            row_cells[0].text = stage_name
            
            # 状态
            row_cells[1].text = node.get_status_display()
            
            # 时间
            if node.status == 'PENDING':
                row_cells[2].text = "-"
            else:
                row_cells[2].text = node.updated_at.strftime('%Y-%m-%d')
            
            # 备注
            row_cells[3].text = node.remark or "-"
