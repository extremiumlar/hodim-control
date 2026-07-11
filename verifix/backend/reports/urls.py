from django.urls import path
from .views import attendance_xlsx, payroll_xlsx, payroll_pdf

urlpatterns = [
    path("attendance.xlsx", attendance_xlsx, name="report-attendance-xlsx"),
    path("payroll.xlsx", payroll_xlsx, name="report-payroll-xlsx"),
    path("payslip/<int:payroll_id>.pdf", payroll_pdf, name="report-payslip-pdf"),
]
