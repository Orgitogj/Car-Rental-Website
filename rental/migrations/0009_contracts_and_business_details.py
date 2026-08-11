import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rental', '0008_tighten_domain_constraints'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='legal_name',
            field=models.CharField(blank=True, max_length=150, verbose_name='Legal business name'),
        ),
        migrations.AddField(
            model_name='company',
            name='state',
            field=models.CharField(blank=True, max_length=80, verbose_name='State'),
        ),
        migrations.AddField(
            model_name='company',
            name='tax_number',
            field=models.CharField(blank=True, max_length=40, verbose_name='Tax number'),
        ),
        migrations.AddField(
            model_name='company',
            name='tin',
            field=models.CharField(blank=True, max_length=40, verbose_name='TIN'),
        ),
        migrations.AlterField(
            model_name='auditlog',
            name='action',
            field=models.CharField(choices=[('company.created', 'Company created'), ('company.updated', 'Company updated'), ('company.deleted', 'Company deleted'), ('company.status_changed', 'Company status changed'), ('company.viewed', 'Company dashboard opened (read-only)'), ('vehicle.created', 'Vehicle added'), ('vehicle.updated', 'Vehicle updated'), ('vehicle.deleted', 'Vehicle removed'), ('booking.created', 'Booking created'), ('booking.confirmed', 'Booking confirmed'), ('booking.cancelled', 'Booking cancelled'), ('contract.created', 'Contract issued'), ('contract.viewed', 'Contract opened'), ('contract.signed', 'Contract signed'), ('contract.version_created', 'Contract version published'), ('contract.renewal_required', 'Contract renewal required'), ('user.activated', 'User activated'), ('user.deactivated', 'User deactivated'), ('report.exported', 'Report exported'), ('access.denied', 'Unauthorised action blocked')], max_length=50),
        ),
        migrations.CreateModel(
            name='ContractTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.CharField(max_length=20, unique=True)),
                ('title', models.CharField(max_length=150)),
                ('summary', models.CharField(blank=True, max_length=255)),
                ('body', models.TextField(help_text='Plain text. A line starting with ## becomes a section heading; a blank line starts a new paragraph.')),
                ('is_active', models.BooleanField(default=False)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='contract_templates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CompanyContract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(editable=False, max_length=32, unique=True)),
                ('version', models.CharField(max_length=20)),
                ('title', models.CharField(max_length=150)),
                ('content', models.TextField()),
                ('content_hash', models.CharField(editable=False, max_length=64)),
                ('status', models.CharField(choices=[('pending_signature', 'Pending signature'), ('signed', 'Signed'), ('rejected', 'Rejected'), ('expired', 'Expired')], db_index=True, default='pending_signature', max_length=24)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('first_viewed_at', models.DateTimeField(blank=True, null=True)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('signer_name', models.CharField(blank=True, max_length=150)),
                ('signer_email', models.EmailField(blank=True, max_length=254)),
                ('signature_name', models.CharField(blank=True, help_text='What the signer typed as their signature.', max_length=150)),
                ('signature_hash', models.CharField(blank=True, editable=False, max_length=64)),
                ('signature_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('signature_user_agent', models.CharField(blank=True, max_length=400)),
                ('rejected_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_reason', models.CharField(blank=True, max_length=255)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contracts', to='rental.company')),
                ('signed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='signed_contracts', to=settings.AUTH_USER_MODEL)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='contracts', to='rental.contracttemplate')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CompanyDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('content_type', models.CharField(blank=True, max_length=100)),
                ('size', models.PositiveIntegerField(default=0)),
                ('data', models.BinaryField(editable=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='rental.company')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_documents', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-uploaded_at'],
                'indexes': [models.Index(fields=['company', '-uploaded_at'], name='rental_comp_company_e1f9ed_idx')],
            },
        ),
        migrations.AddIndex(
            model_name='contracttemplate',
            index=models.Index(fields=['-created_at'], name='rental_cont_created_17232c_idx'),
        ),
        migrations.AddIndex(
            model_name='contracttemplate',
            index=models.Index(fields=['is_active'], name='rental_cont_is_acti_023361_idx'),
        ),
        migrations.AddIndex(
            model_name='companycontract',
            index=models.Index(fields=['company', '-created_at'], name='rental_comp_company_a52081_idx'),
        ),
        migrations.AddIndex(
            model_name='companycontract',
            index=models.Index(fields=['status', '-created_at'], name='rental_comp_status_4b071b_idx'),
        ),
        migrations.AddConstraint(
            model_name='companycontract',
            constraint=models.UniqueConstraint(fields=('company', 'template'), name='one_contract_per_company_version'),
        ),
    ]
