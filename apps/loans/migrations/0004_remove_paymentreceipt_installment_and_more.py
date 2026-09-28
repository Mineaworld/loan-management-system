from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("loans", "0003_paymentreceipt"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="paymentreceipt",
                    name="installment",
                ),
                migrations.RemoveField(
                    model_name="paymentreceipt",
                    name="loan",
                ),
                migrations.RemoveField(
                    model_name="paymentreceipt",
                    name="payer",
                ),
                migrations.RemoveField(
                    model_name="paymentreceipt",
                    name="verified_by",
                ),
                migrations.DeleteModel(
                    name="LoanInstallment",
                ),
                migrations.DeleteModel(
                    name="PaymentReceipt",
                ),
            ],
            database_operations=[]
        )
    ]
