/**
 * Interactive Calendar Script for IUT Appointment System
 */

class AppointmentCalendar {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.currentDate = new Date();
        this.selectedDate = null;
        this.view = options.view || 'month'; // 'month' or 'week'
        this.officerId = options.officerId || null;
        this.onDateSelect = options.onDateSelect || null;
        this.availableSlots = {};
        this.bookedSlots = {};
        this.unavailableDates = [];
        
        this.init();
    }

    init() {
        this.render();
        this.attachEventListeners();
    }

    render() {
        if (this.view === 'month') {
            this.renderMonthView();
        } else if (this.view === 'week') {
            this.renderWeekView();
        }
    }

    renderMonthView() {
        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();
        
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const daysInMonth = lastDay.getDate();
        const startingDayOfWeek = firstDay.getDay();

        let html = `
            <div class="calendar-container">
                <div class="calendar-header">
                    <button class="btn btn-sm btn-outline-primary" id="prev-month">← Previous</button>
                    <h3 id="month-year">${this.getMonthName(month)} ${year}</h3>
                    <button class="btn btn-sm btn-outline-primary" id="next-month">Next →</button>
                </div>
                <div class="calendar-view">
                    <div class="calendar-weekdays">
                        <div class="weekday">Sun</div>
                        <div class="weekday">Mon</div>
                        <div class="weekday">Tue</div>
                        <div class="weekday">Wed</div>
                        <div class="weekday">Thu</div>
                        <div class="weekday">Fri</div>
                        <div class="weekday">Sat</div>
                    </div>
                    <div class="calendar-days">
        `;

        // Empty cells for days before the first day of the month
        for (let i = 0; i < startingDayOfWeek; i++) {
            html += '<div class="calendar-day empty"></div>';
        }

        // Days of the month
        for (let day = 1; day <= daysInMonth; day++) {
            const date = new Date(year, month, day);
            const dateString = this.formatDate(date);
            const isToday = this.isToday(date);
            const isUnavailable = this.isUnavailable(date);
            const isBooked = this.isBooked(dateString);
            const isAvailable = this.isAvailable(dateString);

            let dayClass = 'calendar-day';
            if (isToday) dayClass += ' today';
            if (isUnavailable) dayClass += ' unavailable';
            if (isBooked) dayClass += ' booked';
            if (isAvailable) dayClass += ' available';

            html += `
                <div class="${dayClass}" data-date="${dateString}">
                    <span class="day-number">${day}</span>
                    <span class="day-status">
                        ${isUnavailable ? '✗' : isBooked ? '◐' : isAvailable ? '✓' : ''}
                    </span>
                </div>
            `;
        }

        html += `
                    </div>
                </div>
                <div class="calendar-legend">
                    <div class="legend-item"><span class="legend-color available"></span> Available</div>
                    <div class="legend-item"><span class="legend-color booked"></span> Booked</div>
                    <div class="legend-item"><span class="legend-color unavailable"></span> Unavailable</div>
                </div>
            </div>
        `;

        this.container.innerHTML = html;
    }

    renderWeekView() {
        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();
        const date = this.currentDate.getDate();
        
        const currentDate = new Date(year, month, date);
        const firstDay = new Date(currentDate);
        firstDay.setDate(currentDate.getDate() - currentDate.getDay());

        let html = `
            <div class="calendar-container week-view">
                <div class="calendar-header">
                    <button class="btn btn-sm btn-outline-primary" id="prev-week">← Previous Week</button>
                    <h3 id="week-range">${this.formatDate(firstDay)} - ${this.formatDate(new Date(firstDay.getTime() + 6 * 24 * 60 * 60 * 1000))}</h3>
                    <button class="btn btn-sm btn-outline-primary" id="next-week">Next Week →</button>
                </div>
                <div class="calendar-view week-grid">
        `;

        for (let i = 0; i < 7; i++) {
            const dayDate = new Date(firstDay);
            dayDate.setDate(firstDay.getDate() + i);
            const dateString = this.formatDate(dayDate);
            const dayName = this.getDayName(dayDate.getDay());

            html += `
                <div class="week-day">
                    <div class="week-day-header">${dayName}</div>
                    <div class="week-day-date">${dayDate.getDate()}</div>
                    <div class="week-day-slots" data-date="${dateString}">
                        <!-- Slots will be loaded dynamically -->
                    </div>
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;

        this.container.innerHTML = html;
        this.loadWeekSlots();
    }

    attachEventListeners() {
        if (this.view === 'month') {
            document.getElementById('prev-month')?.addEventListener('click', () => this.previousMonth());
            document.getElementById('next-month')?.addEventListener('click', () => this.nextMonth());
            
            document.querySelectorAll('.calendar-day').forEach(day => {
                day.addEventListener('click', (e) => this.selectDate(e.target.closest('.calendar-day')));
            });
        } else if (this.view === 'week') {
            document.getElementById('prev-week')?.addEventListener('click', () => this.previousWeek());
            document.getElementById('next-week')?.addEventListener('click', () => this.nextWeek());
        }
    }

    selectDate(dayElement) {
        if (dayElement.classList.contains('unavailable') || dayElement.classList.contains('empty')) {
            return;
        }

        // Remove previous selection
        document.querySelectorAll('.calendar-day.selected').forEach(el => {
            el.classList.remove('selected');
        });

        // Add selection to clicked day
        dayElement.classList.add('selected');
        this.selectedDate = dayElement.getAttribute('data-date');

        if (this.onDateSelect) {
            this.onDateSelect(this.selectedDate);
        }
    }

    previousMonth() {
        this.currentDate.setMonth(this.currentDate.getMonth() - 1);
        this.render();
        this.attachEventListeners();
    }

    nextMonth() {
        this.currentDate.setMonth(this.currentDate.getMonth() + 1);
        this.render();
        this.attachEventListeners();
    }

    previousWeek() {
        this.currentDate.setDate(this.currentDate.getDate() - 7);
        this.render();
        this.attachEventListeners();
    }

    nextWeek() {
        this.currentDate.setDate(this.currentDate.getDate() + 7);
        this.render();
        this.attachEventListeners();
    }

    loadWeekSlots() {
        if (!this.officerId) return;

        // Load available slots for each day in the week
        document.querySelectorAll('.week-day-slots').forEach(slotsContainer => {
            const date = slotsContainer.getAttribute('data-date');
            this.loadSlots(date, slotsContainer);
        });
    }

    loadSlots(date, container) {
        if (!this.officerId) return;

        fetch(`/api/appointments/available-slots?officer_id=${this.officerId}&date=${date}`)
            .then(response => response.json())
            .then(data => {
                let html = '';
                if (data.slots && data.slots.length > 0) {
                    data.slots.forEach(slot => {
                        html += `<button class="slot-btn" data-time="${slot}">${slot}</button>`;
                    });
                } else {
                    html = '<p class="no-slots">No available slots</p>';
                }
                container.innerHTML = html;
            })
            .catch(error => console.error('Error loading slots:', error));
    }

    setAvailableSlots(dateString, slots) {
        this.availableSlots[dateString] = slots;
        this.render();
    }

    setBookedSlots(dateString, slots) {
        this.bookedSlots[dateString] = slots;
        this.render();
    }

    setUnavailableDates(dates) {
        this.unavailableDates = dates;
        this.render();
    }

    isToday(date) {
        const today = new Date();
        return date.getDate() === today.getDate() &&
               date.getMonth() === today.getMonth() &&
               date.getFullYear() === today.getFullYear();
    }

    isUnavailable(date) {
        return this.unavailableDates.some(d => this.formatDate(new Date(d)) === this.formatDate(date));
    }

    isBooked(dateString) {
        return this.bookedSlots[dateString] && this.bookedSlots[dateString].length > 0;
    }

    isAvailable(dateString) {
        return this.availableSlots[dateString] && this.availableSlots[dateString].length > 0;
    }

    formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    getMonthName(month) {
        const months = ['January', 'February', 'March', 'April', 'May', 'June',
                       'July', 'August', 'September', 'October', 'November', 'December'];
        return months[month];
    }

    getDayName(dayIndex) {
        const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        return days[dayIndex];
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AppointmentCalendar;
}
