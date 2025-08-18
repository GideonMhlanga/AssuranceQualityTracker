import streamlit as st
import datetime as dt
import pandas as pd
import numpy as np
from database import save_torque_tamper_data, save_net_content_data, save_quality_check_data

def display_torque_tamper_form(username, start_time, check_id):
    """Display and process the Torque and Tamper Evidence form with historical time support"""
    st.subheader("Torque and Tamper Evidence Check")
    st.write(f"Check ID: {check_id}")
    
    with st.form("torque_tamper_form"):
        # Historical timestamp selection
        st.write("#### Measurement Timestamp")
        col1, col2 = st.columns(2)
        with col1:
            # Default to the provided start_time's date, or today if not available
            default_date = start_time.date() if isinstance(start_time, dt.datetime) else dt.date.today()
            entry_date = st.date_input(
                "Date", 
                value=default_date,
                min_value=dt.date(2000, 1, 1),  # Earliest allowed date
                max_value=dt.date.today()       # Can't select future dates
            )
        with col2:
            # Default to the provided start_time's time, or current time if not available
            default_time = (start_time.time() if isinstance(start_time, dt.datetime) 
                          else dt.datetime.now().time())
            entry_time = st.time_input("Time", value=default_time)
        
        # Combine into final timestamp - this will be used as start_time in the database
        measurement_timestamp = dt.datetime.combine(entry_date, entry_time)
        st.caption("Adjust for historical records or leave as-is for current time")
        st.write(f"**Measurement will be recorded for:** {measurement_timestamp.strftime('%Y-%m-%d %H:%M')}")
        
        st.write("#### Torque Values (5-12 range)")
        col1, col2 = st.columns(2)
        
        with col1:
            head1_torque = st.number_input("Rotary Head 1 Torque", min_value=0.0, max_value=20.0, step=1.0, value=1.0)
            head2_torque = st.number_input("Rotary Head 2 Torque", min_value=0.0, max_value=20.0, step=1.0, value=1.0)
            head3_torque = st.number_input("Rotary Head 3 Torque", min_value=0.0, max_value=20.0, step=1.0, value=1.0)
        
        with col2:
            head4_torque = st.number_input("Rotary Head 4 Torque", min_value=0.0, max_value=20.0, step=1.0, value=1.0)
            head5_torque = st.number_input("Rotary Head 5 Torque", min_value=0.0, max_value=20.0, step=1.0, value=1.0)
        
        st.write("#### Tamper Evidence")
        tamper_evidence = st.radio(
            "Tamper Evidence Status",
            options=["PASS (Seal INTACT)", "FAIL (Seal BROKEN)"],
            index=0  # Default to PASS
        )
        
        comments = st.text_area("Comments", height=100, placeholder="Enter any additional notes...")
        
        submit_button = st.form_submit_button("Submit Check")
        
        if submit_button:
            # Validate form
            if not all([head1_torque, head2_torque, head3_torque, head4_torque, head5_torque]):
                st.error("Please enter all torque values (0 is not a valid entry).")
            else:
                # Check torque values against acceptable range
                torque_values = {
                    'head1_torque': head1_torque,
                    'head2_torque': head2_torque,
                    'head3_torque': head3_torque,
                    'head4_torque': head4_torque,
                    'head5_torque': head5_torque
                }
                
                # Categorize out-of-range values
                below_range = {head: val for head, val in torque_values.items() if val < 5}
                above_range = {head: val for head, val in torque_values.items() if val > 12}
                
                # Prepare detailed feedback
                messages = []
                if below_range:
                    messages.append(f"LOW TORQUE: {', '.join([f'{head} ({val} Nm)' for head, val in below_range.items()])}")
                if above_range:
                    messages.append(f"HIGH TORQUE: {', '.join([f'{head} ({val} Nm)' for head, val in above_range.items()])}")
                
                # Save data regardless of being in range (for process analysis)
                data = {
                    'check_id': check_id,
                    'username': username,
                    'timestamp': measurement_timestamp,
                    'start_time': start_time,
                    'head1_torque': head1_torque,  # Changed from 'Head 1'
                    'head2_torque': head2_torque,  # Changed from 'Head 2'
                    'head3_torque': head3_torque,  # Changed from 'Head 3'
                    'head4_torque': head4_torque,  # Changed from 'Head 4'
                    'head5_torque': head5_torque,  # Changed from 'Head 5'
                    'average_torque': sum(torque_values.values()) / len(torque_values),
                    'min_torque': min(torque_values.values()),
                    'max_torque': max(torque_values.values()),
                    'below_range': below_range,
                    'above_range': above_range,
                    'tamper_evidence': tamper_evidence,
                    'comments': comments,
                    'is_within_spec': not (below_range or above_range)
                }
                
                if save_torque_tamper_data(data):  # Your save function
                    if messages:
                        st.warning("Check saved with out-of-range values (process monitoring):")
                        for msg in messages:
                            st.warning(msg)
                        st.info("These values have been recorded for process analysis.")
                    else:
                        st.success("All torque values within specification (5-12 Nm). Data saved successfully!")
                    
                    st.session_state.form_type = None
                    st.rerun()
                else:
                    st.error("Failed to save torque check data. Please try again.")

def display_net_content_form(username, start_time, check_id):
    """Display and process the NET CONTENT form with enhanced volume selection"""
    st.subheader("NET CONTENT Check")
    st.write(f"Check ID: {check_id}")
    st.write(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    with st.form("net_content_form"):
        # Timestamp selection
        st.write("#### Timestamp (for historical data entry)")
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("Date", value=dt.date.today(), key="net_date")
        with col2:
            entry_time = st.time_input("Time", value=dt.datetime.now().time(), key="net_time")
        
        custom_timestamp = dt.datetime.combine(entry_date, entry_time)
        st.caption("Leave at current date/time for real-time entries or adjust for historical data")
        
        # Measurement inputs
        col1, col2 = st.columns(2)
        
        with col1:
            brix = st.number_input("BRIX Value", min_value=0.0, step=0.1, format="%.2f")
            titration_acid = st.number_input("Titration Acid", min_value=0.0, step=0.01, 
                                          value=0.0, format="%.2f",
                                          help="Enter value or leave at 0 for Not Applicable")
            density = st.number_input("Density", min_value=0.0, step=0.001, format="%.5f")
        
        with col2:
            tare = st.number_input("Tare", min_value=0.0, step=0.1, format="%.2f")
            
            # Nominal Volume Selection
            VOLUME_OPTIONS = [330, 400, 500, 1000, 2000, 5000]
            nominal_volume = st.selectbox(
                "Nominal Volume (ml)",
                options=VOLUME_OPTIONS,
                index=None,  # No default selection
                placeholder="Select volume...",
                help="Select the nominal volume for this check"
            )
        
        # Bottle weights
        st.write("#### Bottle Weights")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: bottle1_weight = st.number_input("Bottle 1", min_value=0.0, step=0.1, format="%.1f")
        with col2: bottle2_weight = st.number_input("Bottle 2", min_value=0.0, step=0.1, format="%.1f")
        with col3: bottle3_weight = st.number_input("Bottle 3", min_value=0.0, step=0.1, format="%.1f")
        with col4: bottle4_weight = st.number_input("Bottle 4", min_value=0.0, step=0.1, format="%.1f")
        with col5: bottle5_weight = st.number_input("Bottle 5", min_value=0.0, step=0.1, format="%.1f")
        
        # Calculate average weight
        bottle_weights = [bottle1_weight, bottle2_weight, bottle3_weight, bottle4_weight, bottle5_weight]
        if all(w > 0 for w in bottle_weights):
            average_weight = sum(bottle_weights) / len(bottle_weights)
            st.metric("Average Weight", f"{average_weight:.2f}")
        else:
            average_weight = 0.0
            st.info("Enter all bottle weights to calculate the average")
        
        net_content = average_weight - tare
        st.metric("Net Content", value=f"{net_content:.2f}")  # Shows with 2 decimal places
        comments = st.text_area("Comments", height=100)
        
        # Submit button - must be at the bottom of the form
        submit_button = st.form_submit_button("Submit Check")
        
        if submit_button:
            if not all([brix, density, tare, nominal_volume] + bottle_weights):
                st.error("Please enter all required values.")
            else:
                data = {
                    'check_id': check_id,
                    'username': username,
                    'timestamp': custom_timestamp,
                    'start_time': start_time,
                    'brix': brix,
                    'titration_acid': titration_acid if titration_acid > 0 else None,
                    'density': density,
                    'tare': tare,
                    'nominal_volume': nominal_volume,
                    'bottle1_weight': bottle1_weight,
                    'bottle2_weight': bottle2_weight,
                    'bottle3_weight': bottle3_weight,
                    'bottle4_weight': bottle4_weight,
                    'bottle5_weight': bottle5_weight,
                    'average_weight': average_weight,
                    'net_content': net_content,
                    'comments': comments
                }
                
                if save_net_content_data(data):
                    st.success("Check data saved successfully!")
                    st.session_state.form_type = None
                    st.rerun()
                else:
                    st.error("Failed to save check data. Please try again.")

def display_quality_check_form(username, start_time, check_id):
    """Display and process the 30-Minute Quality Check form"""
    st.subheader("30-Minute Quality Check")
    st.write(f"Check ID: {check_id}")
    st.write(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    with st.form("quality_check_form"):
        # Add timestamp selection for historical data entry
        st.write("#### Timestamp (for historical data entry)")
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("Date", value=dt.date.today(), key="quality_date")
        with col2:
            entry_time = st.time_input("Time", value=dt.datetime.now().time(), key="quality_time")
        
        custom_timestamp = dt.datetime.combine(entry_date, entry_time)
        st.caption("Leave at current date/time for real-time entries or adjust for historical data")
        
        # Product Information
        st.write("#### Product Information")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            trade_name = st.selectbox("Trade Name", ["Mazoe", "Fruitade", "Bonaqua", "Schweppes"])
            
            product_options = {
                "Mazoe": ["Blackberry", "Raspberry", "Orange Crush", "Orange", "Peach", "Guava"],
                "Fruitade": ["Blackberry", "Raspberry", "Cream Soda", "Peach", "Guava"],
                "Bonaqua": ["Bonaqua Water"],
                "Schweppes": ["Schweppes Still Water"]
            }
            
            product = st.selectbox("Product", product_options[trade_name])
            
        with col2:
            volume_options = ["330ml", "500ml", "1000ml", "2000ml", "5000ml"]
            volume = st.text_input("Volume", help="Enter the volume (e.g., 500ml, 1L, 2L)")
            st.caption("Common volumes: " + ", ".join(volume_options))
            cap_colour = st.selectbox("Cap Colour", ["Green", "Brown"])
            
        with col3:
            best_before = st.date_input("Best Before", 
                                       min_value=dt.date.today())
            manufacturing_date = st.date_input("Manufacturing Date", 
                                              max_value=dt.date.today())
        
        # Technical Measurements
        st.write("#### Technical Measurements")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            tare = st.number_input("TARE Scale Value", min_value=0.0, step=0.1)
            brix = st.number_input("BRIX", min_value=0.0, step=0.1)
            
        with col2:
            tank_number = st.selectbox("TANK Number", ["2", "2A"])
            label_type = st.selectbox("Label Type", ["Local", "Export", "Less Sugar"])
            
        with col3:
            label_application = st.selectbox("Label Application", ["OK", "Not OK"])
            torque_test = st.selectbox("Torque Test", ["PASS", "FAIL"])
            
        with col4:
            pack_size = st.selectbox("Pack Size", 
                                    ["6 x 2L", "2 x 5L", "12 x 500ml", "12 x 400ml"])
            pallet_check = st.selectbox("Pallet Check", ["OK", "Not OK"])
        
        # Quality Checks
        st.write("#### Quality Checks")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            date_code = st.selectbox("Date Code", ["OK", "Not OK"])
            odour = st.selectbox("Odour", ["Normal", "Bad Odour"])
            appearance = st.selectbox("Appearance", ["To Std", "Not To Std"])
            product_taste = st.selectbox("Product O/Taste", ["To Std", "Not To Std"])
            
        with col2:
            filler_height = st.selectbox("Filler Height", ["To Std", "Not To Std"])
            keepers_sample = st.selectbox("Keepers Sample", ["Collected", "Not Collected"])
            colour_taste_sample = st.selectbox("Colour Taste Sample", ["Collected", "Not Collected"])
            micro_sample = st.selectbox("Micro Sample", ["Collected", "Not Collected"])
            
        with col3:
            bottle_check = st.selectbox("Bottle Check", ["OK", "Not OK"])
            bottle_seams = st.selectbox("Bottle Seams", ["OK", "Not OK"])
            foreign_material_test = st.selectbox("Foreign Material Test", ["Conducted", "Not Conducted"])
            
        # Container Checks
        st.write("#### Container Checks")
        
        col1, col2 = st.columns(2)
        
        with col1:
            container_rinse_inspection = st.selectbox("Container Rinse Inspection", ["OK", "Not OK"])
            
        with col2:
            container_rinse_water_odour = st.selectbox("Container Rinse Water Odour", ["Normal", "Bad Odour"])
        
        # Comments
        comments = st.text_area("Comments", height=100)
        
        submit_button = st.form_submit_button("Submit Check")
        
        if submit_button:
            # Prepare data for saving
            data = {
                'check_id': check_id,
                'username': username,
                'timestamp': custom_timestamp,  # Use custom timestamp for historical data entry
                'start_time': start_time,
                'trade_name': trade_name,
                'product': product,
                'volume': volume,
                'best_before': best_before,
                'manufacturing_date': manufacturing_date,
                'cap_colour': cap_colour,
                'tare': tare,
                'brix': brix,
                'tank_number': tank_number,
                'label_type': label_type,
                'label_application': label_application,
                'torque_test': torque_test,
                'pack_size': pack_size,
                'pallet_check': pallet_check,
                'date_code': date_code,
                'odour': odour,
                'appearance': appearance,
                'product_taste': product_taste,
                'filler_height': filler_height,
                'keepers_sample': keepers_sample,
                'colour_taste_sample': colour_taste_sample,
                'micro_sample': micro_sample,
                'bottle_check': bottle_check,
                'bottle_seams': bottle_seams,
                'foreign_material_test': foreign_material_test,
                'container_rinse_inspection': container_rinse_inspection,
                'container_rinse_water_odour': container_rinse_water_odour,
                'comments': comments
            }
            
            # Save data to database
            if save_quality_check_data(data):
                st.success("Check data saved successfully!")
                
                # Flag any quality issues
                quality_issues = []
                
                if label_application == "Not OK":
                    quality_issues.append("Label Application")
                    
                if torque_test == "FAIL":
                    quality_issues.append("Torque Test")
                    
                if pallet_check == "Not OK":
                    quality_issues.append("Pallet Check")
                    
                if date_code == "Not OK":
                    quality_issues.append("Date Code")
                    
                if odour == "Bad Odour":
                    quality_issues.append("Product Odour")
                    
                if appearance == "Not To Std":
                    quality_issues.append("Product Appearance")
                    
                if product_taste == "Not To Std":
                    quality_issues.append("Product Taste")
                    
                if filler_height == "Not To Std":
                    quality_issues.append("Filler Height")
                    
                if bottle_check == "Not OK":
                    quality_issues.append("Bottle Check")
                    
                if bottle_seams == "Not OK":
                    quality_issues.append("Bottle Seams")
                    
                if container_rinse_inspection == "Not OK":
                    quality_issues.append("Container Rinse")
                    
                if container_rinse_water_odour == "Bad Odour":
                    quality_issues.append("Rinse Water Odour")
                
                if quality_issues:
                    st.warning(f"Quality issues detected: {', '.join(quality_issues)}")
                
                # Reset form
                st.session_state.form_type = None
                st.rerun()
            else:
                st.error("Failed to save check data. Please try again.")
