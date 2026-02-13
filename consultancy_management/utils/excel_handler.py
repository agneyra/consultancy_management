import pandas as pd
from werkzeug.security import generate_password_hash
from models.database import db
from models.user import User
from models.student import Student
from models.consultancy import Consultancy
import random
import string
from utils.hostels import HOSTELS

def generate_password(length=8):
    """Generate a random password"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

# Updated import_students_from_excel function in utils/excel_handler.py

def import_students_from_excel(file_path):
    """
    Import students from Excel file
    Expected columns: PRN, Name, Branch, Email, Phone, Hostel_Code, Total_Fees, Fees_Paid, Pending_Fee
    """
    try:
        df = pd.read_excel(file_path)
        
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        
        required_columns = ['PRN', 'Name', 'Branch', 'Email', 'Phone', 'Hostel_Code', 'Total_Fees']
        
        # Check if all required columns exist
        for col in required_columns:
            if col not in df.columns:
                return False, f"Missing required column: {col}"
        
        results = {
            'success': 0,
            'failed': 0,
            'errors': [],
            'credentials': []
        }
        
        for index, row in df.iterrows():
            try:
                # Get or create consultancy
                # 🔥 Hostel code from Excel
                hostel_code = str(row['Hostel_Code']).strip().upper()

                # 1️⃣ Validate hostel code against predefined list
                if hostel_code not in HOSTELS:
                    results['failed'] += 1
                    results['errors'].append(
                        f"Row {index+2}: Invalid hostel code '{hostel_code}'"
                    )
                    continue

                # 2️⃣ Find existing consultancy by hostel_code
                consultancy = Consultancy.query.filter_by(hostel_code=hostel_code).first()

                # 3️⃣ Auto-create consultancy if missing
                if not consultancy:
                    consultancy = Consultancy(
                        hostel_code=hostel_code,
                        name=HOSTELS[hostel_code],  # AUTO name from mapping
                        contact_person="Auto Imported",
                        email=f"{hostel_code.lower()}@auto.local",
                        phone="0000000000",
                        address="Auto created from Excel import",
                        is_active=True
                    )
                    db.session.add(consultancy)
                    db.session.flush()  # REQUIRED to get consultancy.id

                
                # Check if student already exists
                existing_student = Student.query.filter_by(prn=str(row['PRN']).strip()).first()
                if existing_student:
                    results['failed'] += 1
                    results['errors'].append(f"Row {index+2}: Student with PRN {row['PRN']} already exists")
                    continue
                
                # Get phone number from Excel
                phone_number = str(row.get('Phone', '')).strip()
                
                # Validate phone number exists
                if not phone_number:
                    results['failed'] += 1
                    results['errors'].append(f"Row {index+2}: Phone number is required")
                    continue
                
                # Get fees data
                total_fees = float(row['Total_Fees'])
                fees_paid = float(row.get('Fees_Paid', 0))  # Default to 0 if not provided
                
                # Validate fees
                if fees_paid > total_fees:
                    results['failed'] += 1
                    results['errors'].append(f"Row {index+2}: Fees paid cannot exceed total fees")
                    continue
                
                # Username is PRN, Password is Phone Number
                username = str(row['PRN']).strip()
                password = phone_number  # Password is the phone number
                
                # Create user
                user = User(
                    username=username,
                    password=generate_password_hash(password),
                    email=str(row['Email']).strip(),
                    role='student',
                    consultancy_id=consultancy.id
                )
                db.session.add(user)
                db.session.flush()
                
                # Create student
                student = Student(
                    user_id=user.id,
                    consultancy_id=consultancy.id,
                    prn=str(row['PRN']).strip(),
                    full_name=str(row['Name']).strip(),
                    branch=str(row['Branch']).strip(),
                    email=str(row['Email']).strip(),
                    phone=phone_number,
                    total_fees=total_fees,
                    fees_paid=fees_paid
                )
                db.session.add(student)
                
                # Store credentials for display
                results['credentials'].append({
                    'prn': str(row['PRN']).strip(),
                    'name': str(row['Name']).strip(),
                    'username': username,
                    'password': password,  # Show phone number as password
                    'email': str(row['Email']).strip(),
                    'phone': phone_number
                })
                
                results['success'] += 1
                
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Row {index+2}: {str(e)}")
                db.session.rollback()
                continue
        
        db.session.commit()
        return True, results
        
    except Exception as e:
        db.session.rollback()
        return False, f"Error processing Excel file: {str(e)}"
    
def export_students_to_excel(students):
    """Export students data to Excel"""
    data = []
    for student in students:
        data.append({
            'PRN': student.prn,
            'Name': student.full_name,
            'Branch': student.branch,
            'Email': student.email,
            'Phone': student.phone,
            'Hostel_Code': f"{student.consultancy.hostel_code} - {student.consultancy.hostel_name}",
            'Total Fees': student.total_fees,
            'Fees Paid': student.fees_paid,
            'Fees Pending': student.fees_pending
        })
    
    df = pd.DataFrame(data)
    return df

def export_transactions_to_excel(transactions):
    """Export transactions to Excel"""
    data = []
    for txn in transactions:
        data.append({
            'Transaction ID': txn.transaction_id,
            'Student Name': txn.student.full_name,
            'PRN': txn.student.prn,
            'Branch': txn.student.branch,
            'Amount': txn.amount,
            'Payment Date': txn.payment_date.strftime('%Y-%m-%d %H:%M:%S'),
            'Status': txn.status
        })
    
    df = pd.DataFrame(data)
    # Sort alphabetically by student name
    df = df.sort_values('Student Name')
    return df