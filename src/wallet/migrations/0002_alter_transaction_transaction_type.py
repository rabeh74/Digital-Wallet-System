# Generated by Django 4.2.7 on 2025-04-12 04:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='transaction_type',
            field=models.CharField(choices=[('DEP', 'Deposit'), ('WTH', 'Withdrawal'), ('TIN', 'Transfer In'), ('TOUT', 'Transfer Out')], max_length=10),
        ),
    ]
