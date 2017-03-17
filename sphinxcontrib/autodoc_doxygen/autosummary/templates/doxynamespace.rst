.. autodoxyclass:: {{ fullname }}
   :members:

   {% if methods %}
   ---------------------
   Functions/Subroutines
   ---------------------

   .. autodoxysummary::
   {% for item in methods %}
      ~{{ fullname }}::{{ item }}
   {%- endfor %}
   {% endif %}
