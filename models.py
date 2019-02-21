from django.db import models
from django.contrib.auth import get_user_model
from system.models import City
import datetime
import re
import uuid
from django.utils import timezone
import decimal
# Create your models here.
class Transaction(models.Model):
	source = models.ForeignKey("Account", on_delete=models.PROTECT, related_name="Tsource")#, editable=False)
	destination = models.ForeignKey("Account", on_delete=models.PROTECT, related_name="Tdestination")#, editable=False)
	amount = models.DecimalField(max_digits=20, decimal_places=2)
	date = models.DateTimeField(auto_now_add=True)#,editable=False)
	tid = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
	note = models.TextField(null=True)
class Customer(models.Model):
	idn = models.UUIDField(default = uuid.uuid4, editable=False)
	user = models.ForeignKey(get_user_model(),null=True ,on_delete=models.PROTECT)
	address = models.CharField(max_length=50)
	ville = models.ForeignKey(City,on_delete=models.PROTECT)
	dob = models.DateField()
	phone = models.CharField(max_length=13)
	active = models.BooleanField(default=True)
	def get_primary(self):
		accounts = self.account_set.all()
		for account in accounts:
			if account.primary == True:
				return account
		return None
	def __str__(self):
		return self.user.first_name +" "+ self.user.last_name
	def internal_transfer(self,source,destination,amount):
		#602 account does not exist
		#603 account does not belong
		#601 Insufisent funds
		#604 same account
		#700 invalid amount
		if amount<0.01:
			return "700"
		if source == destination:
			return "604"
		if source == None or destination==None:
			return "602"
		if source.customer.user != self.user or destination.customer.user != self.user:
			return "603"
		if source.funds_available(amount):
			source.credit(amount)
			destination.load(amount)
			transaction = Transaction.objects.create(source=source,destination=destination,amount=amount)
			sreport = TransactionReport.objects.create(account=source,issender=True,isinternal=True,transaction=transaction)
			rreport = TransactionReport.objects.create(account=destination,issender=False,isinternal=True,transaction=transaction)
			return "200"
		else:
			return "601"
	def external_transfer(self,account,customer,amount):
		if amount<0.01:
			return "700"
		if account == None or customer == None:
			return "602"
		if account.customer.user != self.user:
			return "603"
		if customer.get_primary() == None:
			Account.objects.create(name="Primary",customer=customer,balance=0,primary=True)
			print("A primary account was created")
		if account.funds_available(amount):
			account.credit(amount)
			customer.get_primary().load(amount)
			transaction = Transaction.objects.create(source=account,destination=customer.get_primary(),amount=amount)
			TransactionReport.objects.create(account=account,issender=True,transaction=transaction,isinternal=False)
			TransactionReport.objects.create(account=customer.get_primary(),issender=False,transaction=transaction,isinternal=False)
			return transaction.tid
		else:
			return "601"
class Account(models.Model):
	name = models.CharField(max_length=20)
	customer = models.ForeignKey(Customer,on_delete=models.PROTECT)
	balance = models.DecimalField(max_digits=20, decimal_places=2)
	primary = models.BooleanField(default = False)
	idn = models.UUIDField(default=uuid.uuid4)
	def make_primary(self,uid):
		accounts = Account.objects.filter(customer__user__pk=uid)
		for account in account:
			account.primary = False
		self.primary = True
		self.save()
	def funds_available(self,amount):
		if self.balance>=decimal.Decimal(amount):
			return True
		return False
	def __str__(self):
		return str(self.customer)+"'s account: "+self.name+" solde: "+str(self.balance)
	def load(self,amount):
		self.balance += decimal.Decimal(amount)
		self.save()
	def credit(self,amount):
		self.balance -= decimal.Decimal(amount)
		self.save()
	def send_money(self,destination,amount):
		pass

class TransactionReport(models.Model):
	account = models.ForeignKey(Account,on_delete=models.PROTECT,null=True)
	transaction = models.ForeignKey(Transaction,on_delete=models.PROTECT)
	issender = models.BooleanField()
	isinternal = models.BooleanField(default=False)
	def get_amount(self):
		if self.issender == True:
			return -self.transaction.amount
		else:
			return self.transaction.amount

class MoneyRequest(models.Model):
	by = models.ForeignKey(Customer,on_delete=models.PROTECT,related_name="by")
	to = models.ForeignKey(Customer,on_delete=models.PROTECT,related_name="to")
	amount = models.DecimalField(max_digits=20, decimal_places=2)
	paid = models.BooleanField(default=False)
	date = models.DateTimeField(auto_now_add=True)
	description = models.TextField(null=True,blank=True)
	transaction = models.ForeignKey(Transaction,null=True,on_delete=models.PROTECT)
	def pay(self,account):
		#644 already paid
		#655 the request isn't for you
		if self.paid == True:
			return "644"
		if account.customer != self.to:
			return "655"
		payment = account.customer.external_transfer(account,self.by,self.amount)
		if  len(str(payment))>10:
			self.paid = True
			self.transaction = Transaction.objects.get(tid=payment)
			self.save()
			return "200"
		else:
			return payment
class Invoice(models.Model):
	#654 already assigned
	by = models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='invoice_by')
	to = models.ForeignKey(Customer,on_delete=models.PROTECT,related_name='invoice_to',null=True)
	paid = models.BooleanField(default=False)
	date_created = models.DateTimeField(auto_now_add=True,null=True)
	date_paid = models.DateTimeField(null=True)
	def gettotal(self):
		items = InvoiceItem.objects.filter(Invoice=self)
		total = 0
		for item in items:
			total+=item.gettotal()
		return total
	def pay(self,account):
		if self.to == None:
			self.to = account.customer
			self.save()
		if self.paid == True:
			return "644"
		if account.customer != self.to:
			return "655"
		payment = account.customer.external_transfer(account,self.by,self.amount)
		if  len(str(payment))>10:
			self.paid = True
			self.transaction = Transaction.objects.get(tid=payment)
			self.save()
			return "200"
		else:
			return payment
	def assign(self,customer):
		if self.to != None:
			return "654"
		self.to = customer
		self.save()
		return "200"
class InvoiceItem(models.Model):
	name = models.CharField(max_length=120)
	description = models.TextField()
	amount = models.DecimalField(max_digits=20, decimal_places=2)
	quantity = models.IntegerField()
	invoice = models.ForeignKey(Invoice,on_delete=models.PROTECT)
	def gettotal(self):
		return self.amount*self.quantity