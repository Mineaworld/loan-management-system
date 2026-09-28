from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from apps.accounts.views import officer_required
from apps.reports.services import calculate_nbc_provisioning, calculate_delinquency_metrics, generate_report_csv


@login_required
@officer_required
def nbc_provisioning_api(request):
    prov_data = calculate_nbc_provisioning()
    delinquency_data = calculate_delinquency_metrics()

    tiers_serializable = [
        {
            'tier_key': t['tier_key'],
            'name_km': t['name_km'],
            'name_en': t['name_en'],
            'dpd_range': t['dpd_range'],
            'rate_pct': float(t['rate_pct']),
            'loan_count': t['loan_count'],
            'total_balance': float(t['total_balance']),
            'required_provision': float(t['required_provision']),
        }
        for t in prov_data['tiers']
    ]

    return JsonResponse({
        'success': True,
        'total_loans': prov_data['total_loans'],
        'total_portfolio': float(prov_data['total_portfolio']),
        'total_provision': float(prov_data['total_provision']),
        'par_30_balance': float(delinquency_data['par_30_balance']),
        'par_30_ratio': delinquency_data['par_30_ratio'],
        'par_90_balance': float(delinquency_data['par_90_balance']),
        'par_90_ratio': delinquency_data['par_90_ratio'],
        'collection_rate': delinquency_data['collection_rate'],
        'tiers': tiers_serializable,
    })


@login_required
@officer_required
def export_report_csv_view(request):
    report_type = request.GET.get('type', 'asset_quality')
    if report_type not in ['asset_quality', 'delinquency', 'repayments']:
        report_type = 'asset_quality'

    csv_data = generate_report_csv(report_type)
    filename = f"lms_{report_type}_{timezone.now():%Y%m%d_%H%M}.csv"

    response = HttpResponse(csv_data, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
